import json
import jwt
import datetime
from bson import ObjectId
from pymongo import MongoClient
from flask import Flask, jsonify, request
import os
from werkzeug.exceptions import HTTPException
from functools import wraps

app = Flask(__name__)

# ✅ Load JWT Secret Key from Local Environment (Prevents Crash)
app.config['SECRET_KEY'] = os.environ["JWT_SECRET_KEY"]  

# ✅ MongoDB Configuration
mongo_uri = os.getenv("MONGO_URI")

# ✅ Connection handling optimized for AWS Lambda
client = None
db = None

def initialize_db():
    global client, db
    if not client:
        client = MongoClient(mongo_uri)
        db = client['MyDatabase']
        print(f"Connected to database: {db.name}")

def close_db():
    global client
    if client:
        client.close()
        client = None

def json_converter(user):
    if user and "_id" in user:
        user["_id"] = str(user["_id"])
    return user

# ✅ JWT Authorization Middleware
def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None

        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        if not token:
            return jsonify({"error": "Token is missing!"}), 401

        try:
            decoded_token = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            request.user = decoded_token  # Store decoded user in request
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired!"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token!"}), 401

        return f(*args, **kwargs)
    return decorated_function

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

# ✅ Login Route - Returns JWT Token
@app.route('/login', methods=['POST'])
def login():
    data = request.json

    if not data or not data.get("username") or not data.get("password"):
        return jsonify({"error": "Missing username or password"}), 400

    # Dummy Authentication (Replace with DB check)
    if data["username"] == "admin" and data["password"] == "password":
        # ✅ Add Expiry Time to JWT Token (1 Hour Expiration)
        token = jwt.encode(
            {"user": data["username"], "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}, 
            app.config['SECRET_KEY'], 
            algorithm='HS256'
        )

        return jsonify({"token": token}), 200

    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/users/<int:user_id>', methods=['GET'])
@token_required
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
@token_required
def create_user():
    try:
        initialize_db()
        data = request.json

        if not data or "user_id" not in data or "name" not in data or "email" not in data:
            return jsonify({"error": "Missing required fields"}), 400

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
@token_required
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
@token_required
def delete_user(user_id):
    try:
        initialize_db()
        result = db.users.delete_one({"user_id": user_id})
        if result.deleted_count == 0:
            return jsonify({"error": "User not found"}), 404
        return jsonify({"message": "User deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ AWS Lambda Handler
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
