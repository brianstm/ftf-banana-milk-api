import flask_cors
import os
from elasticsearch import Elasticsearch
from anthropic import AnthropicBedrock
from flask import Flask, jsonify, request, session
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
app.secret_key = "secret_key"

lobbies = {}

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

def request_recommendation(user_preferences):
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

@app.route('/api/create-lobby', methods=['POST'])
def create_lobby():
    lobby_id = random.randint(1000, 9999)
    lobbies[lobby_id] = {"members": [], "interests": {}}
    return jsonify({"lobbyId": lobby_id}), 201

@app.route('/api/join-lobby', methods=['POST'])
def join_lobby():
    data = request.get_json()
    lobby_id = data.get('lobbyId')
    name = data.get('name')
    interests = data.get('interests')

    if not lobby_id or not name or not interests:
        return jsonify({'error': 'Lobby ID, name, and interests are required'}), 400

    lobby = lobbies.get(lobby_id)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404

    if name in [member['name'] for member in lobby['members']]:
        return jsonify({'error': 'User already in lobby'}), 400

    lobby['members'].append({'name': name, 'interests': interests})
    lobby['interests'][name] = interests

    return jsonify({'message': 'User joined lobby'}), 200

@app.route('/lobby/<int:lobby_id>/hub')
def hub(lobby_id):
    lobby = lobbies.get(lobby_id)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404

    display_members = []
    for member in lobby['members']:
        display_members.append({
            'name': member['name'],
            'likes': member['interests']['likes'],
            'dislikes': member['interests']['dislikes']
        })

    return jsonify({'message': f'Lobby hub for lobby {lobby_id}', 'members': display_members, "interests": lobby["interests"]}), 200

@app.route('/lobby/<int:lobby_id>/recommendations')
def get_recommendations(lobby_id):
    lobby = lobbies.get(lobby_id)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404
    all_preferences = ""
    for member in lobby["members"]:
        all_preferences += f"User {member['name']}: Likes: {member['interests']['likes']}, Dislikes: {member['interests']['dislikes']}. "
    recommendations = request_recommendation(all_preferences)
    return jsonify(recommendations)

if __name__ == '__main__':
    app.run(debug=True)
