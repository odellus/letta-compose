from flask import Flask, jsonify, request

app = Flask(__name__)

# Mock user data
users = {
    "1": {"id": "1", "name": "Alice", "email": "alice@example.com"},
    "2": {"id": "2", "name": "Bob", "email": "bob@example.com"}
}

def get_next_id():
    if not users:
        return "1"
    return str(max(int(k) for k in users.keys()) + 1)

@app.route('/users/<user_id>', methods=['GET'])
def get_user(user_id):
    user = users.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)

@app.route('/users', methods=['POST'])
def create_user():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    name = data.get("name")
    email = data.get("email")
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not email:
        return jsonify({"error": "email is required"}), 400
    user_id = get_next_id()
    users[user_id] = {"id": user_id, "name": name, "email": email}
    return jsonify(users[user_id]), 201

@app.route('/users/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    if user_id not in users:
        return jsonify({"error": "User not found"}), 404
    del users[user_id]
    return "", 204

if __name__ == '__main__':
    app.run(debug=True)
