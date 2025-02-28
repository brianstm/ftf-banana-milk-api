
import flask_cors
import os
from elasticsearch import Elasticsearch
from anthropic import AnthropicBedrock
from flask import Flask, jsonify, request, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

client = AnthropicBedrock(
    aws_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_region=os.getenv("AWS_REGION"),
)

context = [
    {
        "role" : "system",
        "content" : "You are a reccomendation system."
    }
]

tools = [
    {
        "name": "event_search",
        "description": "Get an event or destination based on user interest",
        "input_schema": {
            "type": "object",
            "properties": {
                "lobby_type": {
                    "type": "string",
                    "description": "The common denominator between tht users",
                }
            },
            "required": ["location"],
        },
    }
]



app = Flask(__name__)
flask_cors.CORS(app)

users = {}
lobbies = []

es = Elasticsearch(
    "https://my-elasticsearch-project-f37513.es.ap-southeast-1.aws.elastic.cloud:443",
    api_key=os.getenv("ES_API_KEY") 
)

def get_elastic_search():
    query = {
        "size": 50, 
        "query": {
            "match_all": {} 
        }
    }
    
    response = es.search(index="destinations_all", body=query)
    
    places_data = [hit["_source"] for hit in response["hits"]["hits"]]
    return places_data

def request_recommendation(user_preferences): # Returns text response
    context = system_prompt[:]
    context.append(
        [
            {
                "role" : "user",
                "content" : ""
            }
        ]
    )

    response = client.messages.create(
        max_tokens=1024,
        messages=context,
        tools=tools,
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        tool_choice={
            "type" : "tool",
            "name" : "event_search",
        }
    )

    for content in response.content:
        if content["type"] == "tool_use":
            get_elastic_search()

            context.append(None) # add elastic data response

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"message": "It's working!"})

if __name__ == '__main__':
    app.run(debug=True)



#make account

@app.route('/sign_up', method = ['POST'])
def sign_up():
    if request.method == 'POST':
        data = request.get_json()
        if data.get('password') != data.get('confirm_password'):
            return jsonify({'error': 'Passwords do not match'}), 400
        user = {'username': data.get('username'), 'email': data.get('email'), 'password': generate_password_hash(data.get('password'))}
        if user['email'] in users:
            return jsonify({'error': 'Email already in use.Please login or use another email address'}), 400
        if '@' not in user['email']:
            return jsonify({'error': 'Not   a valid email'}), 400
        users[len(users)+1] = user
        return redirect(url_for('login'))

@app.route('/login', method = [''])
def login():
    return 'Login Page'
    
    


#Creates a lobby that people can join
@app.route('/lobby', method = ['POST'])
def new_lobby():
    data = request.get_json()
    user_id = data.get('user_id')

    if not data or 'name' not in data or not user_id:
        return jsonify({'error': 'Name and user_id are required'}), 400

    if user_id not in users:
        return jsonify({'error': 'User does not exist'}), 400

    global lobby_id_counter
    lobby_id = lobby_id_counter
    lobby_id_counter += 1

    private_link = secrets.token_urlsafe(16)

    lobby = {
        'id': lobby_id,
        'name': data['name'],
        'description': data.get('description', ''),
        'creator_id': user_id,
        'members': [user_id],
        'private_link': private_link,
        'password': generate_password_hash(data.get('password'))
    }
    lobbies.append(lobby)
    return jsonify({'message': 'Lobby created', 'lobby_id': lobby_id, 'private_link': private_link}), 201
 
@app.route('/lobby', method = ['GET'])
def get_lobbies():
    return jsonify(lobbies)


#Lobby management
@app.route('/lobby/<int:lobby_id>', methods=['GET'])
def get_lobby(lobby_id):
    lobby = next((lobby for lobby in lobbies if lobby['id'] == lobby_id), None)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404

    members = []
    for member_id in lobby['members']:
        user = users.get(member_id)
        if user:
            members.append({'id': member_id, 'username': user['username']})

    lobby_data = {
        'id': lobby['id'],
        'name': lobby['name'],
        'description': lobby.get('description', ''),
        'creator_id': lobby['creator_id'],
        'members': members
    }
    return jsonify(lobby_data), 200


#join throughh a lobby name and password
@app.route('/lobby/jo')

#join through a link
@app.route('/lobby/<int:lobby_id>/join', methods=['POST'])
def join_lobby(lobby_id):
    data = request.get_json()
    user_id = data.get('user_id')
    
assword = data.get('passwor')
    if not user_id:
        return jsonify({'error': 'User ID is required'}), 400

    if user_id not in users:
        return jsonify({'error': 'User not found'}), 404

    lobby = next((lobby for lobby in lobbies if lobby['id'] == lobby_id), None)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404

    if user_id in lobby['members']:
        return jsonify({'error': 'User already in lobby'}), 400

    lobby['members'].append(user_id)
    return jsonify({'message': 'User joined lobby'}), 200


#hub with all the users
@app.route('/lobby/<int:lobby_id>/hub')
def hub(lobby_id):
    lobby = next((lobby for lobby in lobbies if lobby['id'] == lobby_id), None)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404
    return jsonify({'message': f'Lobby hub for lobby {lobby_id}'}), 200



#make api to suggest based on user’s preferences or group preferecnes

    # Get user preferences
    # Ask LLM to summarize and find common denominator
    # Forward query to Elastic
    # Receive query from Elastic
    # Generate response from Elastic data


