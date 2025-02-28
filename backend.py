import flask_cors
import os
from elasticsearch import Elasticsearch, helpers
from anthropic import AnthropicBedrock
from flask import Flask, jsonify, request
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



system_prompt = [
    {
        "role" : "user",
        "content" : "You are a recommendation system."
    }
]

tools = [
    {
        "name": "event_search",
        "description": "Get an event or destination based on user interest",
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": ["name", "description"],
                    "description": "The field to search for events or destinations",
                },
                "query": {
                    "type": "string",
                    "description": "The query to search for events or destinations",
                }
            },
            "required": ["field", "query"],
        },
    }
]

es = Elasticsearch(
	"https://my-elasticsearch-project-d6a6a8.es.us-west-2.aws.elastic.cloud:443",
	api_key=os.getenv("ES_API_KEY"),
)

client = AnthropicBedrock(
    aws_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_region=os.getenv("AWS_REGION"),
)

def setup_elastic_search():
	index_name = "destinations"

	mappings = {
		"properties" : {
			"name" : {
				"type": "semantic_text"
			},
			"description" : {
				"type": "semantic_text"
			}
		}
	}

	mapping_response = es.indices.put_mapping(index=index_name, body=mappings)
	print(mapping_response)

	docs = []

	with open("destinations.ndjson", "r") as f:
		for line in f:
			if line.strip():
				data = json.loads(line)
				desc = ""
				if data["country"] != "Singapore":
					continue
				for key, value in data.items():
					if key != "name" and value:
						desc += f"- {key}: {value}\n"
				docs.append({
					"name": data["name"],
					"description": desc
				})

	bulk_response = helpers.bulk(es, docs, index=index_name)
	print(bulk_response)

def get_elastic_search(field, query):
	query = {
		"semantic": {
			"field": field,
			"query": query
		}
	}

	response = es.search(index="destinations", query=query)

	places_data = [hit["_source"] for hit in response["hits"]["hits"]]
	return places_data

def request_recommendation(param):
	system_prompt = "You are an assistant that helps users find destinations based on their preferences. Be as specific as you can with the tool params. After receiving the tool response, format the response accordingly and provide the best response."

	context = [
		{
			"role": "user",
			"content": f"Here are the names of the users and their respective likes and dislikes.\n{param}\nDetermine the shared likes and dislikes of the users and query the tool to determine the most likely enjoyable event."
		}
	]

	print("Understanding...")

	response = client.messages.create(
		model="anthropic.claude-3-5-sonnet-20241022-v2:0",
		max_tokens=1024,
		messages=context,
		tools=tools,
		tool_choice={
			"type": "tool",
			"name": "event_search"
		}
	)

	content = response.content[0]
	tool_input = response.content[0].input
	field = tool_input["field"]
	query = tool_input["query"]

	print(f"Searching {field}, {query}...")

	places_data = get_elastic_search(field, query)
	result = "\n".join([f"## {place['name']}\n{place['description']}" for place in places_data])

	print(result)

	return result


app = Flask(__name__)
flask_cors.CORS(app, resources={r"/*": {"origins": "*"}})

lobbies = {}

es = Elasticsearch(
    "https://my-elasticsearch-project-d6a6a8.es.us-west-2.aws.elastic.cloud:443",
    api_key=os.getenv("ES_API_KEY")
)

@app.route('/api/create-lobby', methods=['POST'])
def create_lobby():
    data = request.get_json()
    lobby_id = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    lobbies[lobby_id] = {"lobby_id": lobby_id, "name": data.get(
        "name"), "members": [], "interests": {}}
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


@app.route('/lobby/<lobby_id>/hub')
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


@app.route('/lobby/<lobby_id>/recommendations')
def get_recommendations(lobby_id):
    lobby = lobbies.get(lobby_id)
    if not lobby:
        return jsonify({'error': 'Lobby not found'}), 404
    all_preferences = ""
    for member in lobby["members"]:
        all_preferences += f"User {member['name']}: Likes: {', '.join(member['interests']['likes']) if member['interests']['likes'] else 'None'}, Dislikes: {', '.join(member['interests']['dislikes']) if member['interests']['dislikes'] else 'None'}. "

    print(all_preferences)
    recommendations = request_recommendation(all_preferences)

    print(recommendations)
    return recommendations


@app.route("/")
def home():
    return jsonify({"message": "Welcome to the Lobby API", "lobbies": lobbies})


if __name__ == '__main__':
    app.run(host="0.0.0.0", port="8080", debug=True)