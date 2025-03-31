import json
from bson import ObjectId
from pymongo import MongoClient
from flask import Flask, jsonify, request
import os
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

# MongoDB configuration
mongo_uri = os.getenv("MONGO_URI", "mongodb+srv://harinisri01:hs5229@cluster0.34bgy.mongodb.net/MyDatabase?retryWrites=true&w=majority&appName=Cluster0")

# Connection handling optimized for Lambda
client = None
db = None

def initialize_db():
    global client, db
    if not client:
        client = MongoClient(mongo_uri)
        db = client['MyDatabase']  # Ensure correct database name
        print(f"Connected to database: {db.name}")

def close_db():
    global client
    if client:
        client.close()
        client = None

def json_converter(user):
    if user and "_id" in user:
        user["_id"] = str(user["_id"])  # Convert ObjectId to string
    return user

@app.route('/')
def home():
    return "Welcome to the MongoDB-powered Serverless API!"

@app.route('/debug/routes')
def list_routes():
    output = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(rule.methods)
        output.append(f"{rule.rule} -> {rule.endpoint} ({methods})")
    return jsonify({"routes": output})

@app.route('/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    try:
        initialize_db()
        user = db.users.find_one({"user_id": user_id})
        if not user:
            return jsonify({"error": "User not found"}), 404
        return jsonify(json_converter(user))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/users', methods=['POST'])
def create_user():
    try:
        initialize_db()  # Ensure database is connected
        data = request.json  # Get JSON payload

        if not data or "user_id" not in data or "name" not in data or "email" not in data:
            return jsonify({"error": "Missing required fields"}), 400

        # Insert user into MongoDB
        new_user = {
            "user_id": data["user_id"],
            "name": data["name"],
            "email": data["email"]
        }
        db.users.insert_one(new_user)
        return jsonify({"message": "User created successfully", "user": new_user}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    try:
        initialize_db()
        data = request.get_json()
        result = db.users.update_one({"user_id": user_id}, {"$set": data})
        if result.matched_count == 0:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"message": "User updated successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    try:
        initialize_db()
        result = db.users.delete_one({"user_id": user_id})
        if result.deleted_count == 0:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"message": "User deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def lambda_handler(event, context):
    print("Raw event:", json.dumps(event))
    initialize_db()

    try:
        environ = {
            'REQUEST_METHOD': event['httpMethod'],
            'PATH_INFO': event['path'],
            'QUERY_STRING': event.get("queryStringParameters", "") or "",
            'SERVER_NAME': 'lambda',
            'SERVER_PORT': '80',
            'wsgi.url_scheme': 'https',
            'wsgi.input': None,
            'wsgi.errors': None,
            'wsgi.version': (1, 0),
            'wsgi.multithread': False,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False
        }
        
        for key, value in event.get('headers', {}).items():
            environ[f'HTTP_{key.upper().replace("-", "_")}'] = value
        
        with app.request_context(environ):
            try:
                response = app.full_dispatch_request()
                return {
                    "statusCode": response.status_code,
                    "body": response.get_data(as_text=True),
                    "headers": dict(response.headers)
                }
            except HTTPException as e:
                return {
                    "statusCode": e.code,
                    "body": json.dumps({"error": e.description}),
                    "headers": {"Content-Type": "application/json"}
                }
    except Exception as e:
        print(f"Handler error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
            "headers": {"Content-Type": "application/json"}
        }
    finally:
        close_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

