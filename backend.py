import flask_cors
import os
from elasticsearch import Elasticsearch
from anthropic import AnthropicBedrock
from flask import Flask, jsonify, request, redirect, url_for, session
from dotenv import load_dotenv
import random

load_dotenv()

client = AnthropicBedrock(
    aws_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_region=os.getenv("AWS_REGION"),
)

context = [
    {
        "role": "system",
        "content": "You are a recommendation system."
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
                    "description": "The common denominator between the users",
                }
            },
            "required": ["lobby_type"],
        },
    }
]

app = Flask(__name__)
flask_cors.CORS(app)
app.secret_key = "secret_key"  # Important for sessions

lobbies = {}  # Changed to dictionary for easier lobby ID access

es = Elasticsearch(
    "https://my-elasticsearch-project-f37513.es.ap-southeast-1.aws.elastic.cloud:443",
    api_key=os.getenv("ES_API_KEY")
)

def get_elastic_search(query_term):
    query = {
        "size": 50,
        "query": {
            "match":{
                "description":query_term
            }
        }
    }

    response = es.search(index="destinations_all", body=query)

    places_data = [hit["_source"] for hit in response["hits"]["hits"]]
    return places_data

def request_recommendation(user_preferences):  # Returns text response
    context_copy = context[:]
    context_copy.append(
        {
            "role": "user",
            "content": f"Based on these preferences: {user_preferences}, provide a common interest."
        }
    )

    response = client.messages.create(
        max_tokens=1024,
        messages=context_copy,
        tools=tools,
        model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        tool_choice={
            "type": "tool",
            "name": "event_search",
        }
    )

    for content in response.content:
        if content["type"] == "tool_use":
            arguments = content['input']['arguments']
            search_term = arguments['lobby_type']
            elastic_results = get_elastic_search(search_term)
            return elastic_results

    return "No recommendation found."

@app.route('/status', methods=['GET'])
def status():
    return jsonify({"message": "It's working!"})

@app.route('/lobby', methods=['POST'])
def new_lobby():
    data = request.get_json()
    creator_name = data.get('creator_name')

    if not data or 'name' not in data or not creator_name:
        return jsonify({'error': 'Name and creator_name are required'}), 400

    lobby_id = random.randint(1000, 9999)
    lobbies[lobby_id] = {"name": data['name'], "description": data.get('description', ''), "creator_name": creator_name, "members": [creator_name], "preferences": {}}
    return jsonify({'message': 'Lobby created', 'lobby_id': lobby_id}), 201

@app.route('/lobby', methods=['GET'])
def get_lobbies():
    return jsonify(list(lobbies.values()))

@app.route('/lobby/<int:lobby_id>', methods=['GET'])
def get_lobby(lobby_id):
    lobby = lobbies.get(lobby_id)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404

    lobby_data = {
        'id': lobby_id,
        'name': lobby['name'],
        'description': lobby.get('description', ''),
        'creator_name': lobby['creator_name'],
        'members': lobby['members'],
        'preferences': lobby['preferences']
    }
    return jsonify(lobby_data), 200

@app.route('/lobby/join', methods=['POST'])
def join_lobby():
    data = request.get_json()
    user_name = data.get('user_name')
    lobby_id = data.get('lobby_id')
    preferences = data.get('preferences')

    if not user_name or not lobby_id:
        return jsonify({'error': 'User name and Lobby ID are required'}), 400

    lobby = lobbies.get(lobby_id)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404

    if user_name in lobby['members']:
        return jsonify({'error': 'User already in lobby'}), 400

    lobby['members'].append(user_name)
    lobby['preferences'][user_name] = preferences
    return jsonify({'message': 'User joined lobby'}), 200

@app.route('/lobby/<int:lobby_id>/hub')
def hub(lobby_id):
    lobby = lobbies.get(lobby_id)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404
    return jsonify({'message': f'Lobby hub for lobby {lobby_id}', 'members': lobby['members'], "preferences": lobby["preferences"]}), 200

@app.route('/lobby/<int:lobby_id>/recommendations')
def get_recommendations(lobby_id):
    lobby = lobbies.get(lobby_id)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404
    all_preferences = ""
    for user_name, preference in lobby["preferences"].items():
        all_preferences += f"User {user_name}: {preference}. "
    recommendations = request_recommendation(all_preferences)
    return jsonify(recommendations)

if __name__ == '__main__':
    app.run(debug=True)
