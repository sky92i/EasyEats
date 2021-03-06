import os, requests, json
from flask import Flask, jsonify, request
from pymongo import MongoClient
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
metrics = PrometheusMetrics(app)

try:
    # connect mongodb with the environment variables
    client = MongoClient(f'mongodb://{os.environ.get("MONGO_USERNAME")}:{os.environ.get("MONGO_PASSWORD")}@{os.environ.get("MONGO_SERVER_HOST")}:27017/{os.environ.get("MONGO_DATABASE")}?authSource=admin')
    client.server_info() # check database connection
    print ("[v] Database connection is successful.")
except Exception as e: # print error and exit
    print ("[x] Database connection error.")
    if e.code == 18: print ("[x] Database authentication failed.")
    print ("Error details: ", e.details)

db = client["EasyEats"]

def remove_id(data):
    data.pop('_id')
    return data

@app.route('/')
def home():
    return f"Hello world!"

# Retrieve existing store menu
@app.route('/stores/<store_id>/menus', methods=['GET'])
def get_menu(store_id):
    menu = db.menu.find_one({"store_id": store_id})
    if not menu:
        if not db.store.find_one({"store_id": store_id}):
            return jsonify({"error": "store not found"}), 404
        return jsonify({"error": "menu not found"}), 404
    return jsonify({"items": menu["items"]})

# Create or override the entire menu
@app.route('/stores/<store_id>/menus', methods=['PUT'])
def upload_menu(store_id):
    if not db.store.find_one({"store_id": store_id}):
        return jsonify({"error": "store not found"}), 404
    try:
        if request:
            request_body = request.json
            for item in request_body["items"]:
                if not (("item_id" in item) and ("price" in item) and ("available" in item)):
                    return jsonify({"error": "all items need to have an id, price and availability"}), 400
            if db.menu.find_one({"store_id": store_id}):
                db.menu.replace_one({"store_id": store_id}, {"store_id": store_id, "items": request_body["items"]})
                return jsonify({}), 204
            db.menu.insert_one({"store_id": store_id, "items": request_body["items"]})
            return jsonify({}), 204
    except KeyError:
        return jsonify({"error": "the format of given data is incorrect"}), 400
    except TypeError:
        return jsonify({"error": "the format of given data is incorrect"}), 400
    return jsonify({"error": "store x not found"}), 404

# Update an individual item within a store's menu
@app.route('/stores/<store_id>/menus/items/<item_id>', methods=['POST'])
def update_item(store_id, item_id):
    menu = db.menu.find_one({"store_id": store_id})
    if menu:
        item_id_exists = False
        for item in menu["items"]:
            if item["item_id"] == item_id:
                item_id_exists = True
        if not item_id_exists:
            return jsonify({"error": "the item_id does not exist"}), 404

        allowed_availability = ["yes", "no"]
        try:
            if request:
                request_body = request.json
                if "available" in request_body:
                    if request_body["available"] not in allowed_availability:
                        return jsonify({"error": f"availability keyword " + request_body["available"] + " is not allowed"}), 400
        except KeyError:
            return jsonify({"error": "the format of given data is incorrect"}), 400
        except TypeError:
            return jsonify({"error": "the format of given data is incorrect"}), 400

        request_body = request.json
        new_items = []
        if "available" in request_body:
            if "price" in request_body:
                for item in menu["items"]:
                    if item["item_id"] == item_id:
                        new_items.append({"item_id": item_id, "price": request_body["price"], "available": request_body["available"]})
                    else:
                        new_items.append({"item_id": item["item_id"], "price": item["price"], "available": item["available"]})
                db.menu.update_one({'store_id': store_id}, {'$set': {'items': new_items}})
                return jsonify({}), 204
            else:
                for item in menu["items"]:
                    if item["item_id"] == item_id:
                        new_items.append({"item_id": item_id, "price": item["price"], "available": request_body["available"]})
                    else:
                        new_items.append({"item_id": item["item_id"], "price": item["price"], "available": item["available"]})
                db.menu.update_one({'store_id': store_id}, {'$set': {'items': new_items}})
                return jsonify({}), 204
        if "price" in request_body:
            for item in menu["items"]:
                if item["item_id"] == item_id:
                    new_items.append({"item_id": item_id, "price": request_body["price"], "available": item["available"]})
                else:
                    new_items.append({"item_id": item["item_id"], "price": item["price"], "available": item["available"]})
            db.menu.update_one({'store_id': store_id}, {'$set': {'items': new_items}})
            return jsonify({}), 204
        else:
            return jsonify({"error": "the format of given data is incorrect"}), 400
    return jsonify({"error": "store's menu not found"}), 404

# Retrieve store information
@app.route('/stores/<store_id>', methods=['GET'])
def get_store_details(store_id):
    store = [remove_id(i) for i in db.store.find({"store_id": store_id})]
    if store:
        return jsonify(store[0]), 200
    else:
        return jsonify({"error": "not found"}), 404

# Retrieve all stores
@app.route('/stores', methods=['GET'])
def get_all_stores():
    stores = []
    for store in db.store.find():
        stores.append({"name": store["name"], "store_id": store["store_id"]})
    if not stores:
        return jsonify({"error": "not found"}), 404
    return jsonify(stores), 200

# Retrieve store online status availability
@app.route('/stores/<store_id>/status', methods=['GET'])
def get_restaurant_status(store_id):
    query = db.store.status.find_one({"store_id": store_id})
    if not query:
        return jsonify({"error": "not found"}), 404
    return jsonify({"status": query["status"], "offlineReason": query["offlineReason"]})

# Set store online status availability
@app.route('/stores/<store_id>/status', methods=['POST'])
def set_restaurant_status(store_id):
    cursor = db.store.status.find({'store_id': store_id})
    if cursor.count() > 0:
        data = [remove_id(i) for i in cursor]
        allowed_status = ["ONLINE", "PAUSED", "OFFLINE"]
        allowed_offline_reasons = ["OUT_OF_MENU_HOURS", "INVISIBLE", "PAUSED_BY_UBER", "PAUSED_BY_RESTAURANT"]
        try:
            if request:
                request_body = request.json
                if request_body["status"] not in allowed_status:
                    return jsonify({"error": f"restaurant status " + request_body["status"] + " is not allowed"}), 400
                if request_body["status"] != 'ONLINE' and request_body["reason"] not in allowed_offline_reasons:
                    return jsonify({"error": "must provide a valid offline reason"}), 400
                if not request_body["reason"]:
                    return jsonify({"error": "reason must be given"}), 400
                if not request_body["status"]:
                    return jsonify({"error": "status must be given"}), 400
            else:
                return jsonify({"error": "both status and reason must be given"}), 400
        except KeyError:
            return jsonify({"error": "the format of given data is incorrect"}), 400
        except TypeError:
            return jsonify({"error": "the format of given data is incorrect"}), 400

        if data[0]['status'] == request_body["status"]:         # If the new status is the same as the current one
            return jsonify({"error": f"restaurant status is already " + request_body["status"]}), 400
        else:
            db.store.status.update_one({'store_id': store_id}, {'$set': {'status': request_body["status"], 'offlineReason': request_body["reason"]}})
            return jsonify({}), 204
    return jsonify({"error": "store not found"}), 404

# Retrieve date-specific store hours
@app.route('/stores/<store_id>/holiday-hours', methods=['GET'])
def get_holiday_hours(store_id):
    query = db.store.holiday.find_one({"store_id": store_id})
    if not query:
        return jsonify({"error": "store not found"}), 404
    return jsonify({"holiday_hours": query["holiday_hours"]})

# Set date-specific store hours
@app.route('/stores/<store_id>/holiday-hours', methods=['POST'])
def set_holiday_hours(store_id):
    if not db.store.find_one({"store_id": store_id}):
        return jsonify({"error": "store not found"}), 404
    try:
        if request:
            request_body = request.json
            if db.store.holiday.find_one({"store_id": store_id}):
                db.store.holiday.replace_one({"store_id": store_id}, {"store_id": store_id, "holiday_hours": request_body["holiday_hours"]})
                return jsonify({}), 204
            db.store.holiday.insert_one({"store_id": store_id, "holiday_hours": request_body["holiday_hours"]})
            return jsonify({}), 204
    except KeyError:
        return jsonify({"error": "the format of given data is incorrect"}), 400
    except TypeError:
        return jsonify({"error": "the format of given data is incorrect"}), 400
    return jsonify({"error": "store holiday-hours not found"}), 404

# 404 error handler
@app.errorhandler(404)
def not_found(e):
    return {"error": "not found"}, 404

# 400 error handler
@app.errorhandler(400)
def bad_request(e):
    return {"error": "bad request"}, 400

# 405 error handler
@app.errorhandler(405)
def method_not_allowed(e):
    return {"error": "method not allowed"}, 405

# 500 error handler
@app.errorhandler(500)
def internal_server_error(e):
    return {"error": "internal server error"}, 500

#start flask server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=15000)