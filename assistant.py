from elasticsearch import Elasticsearch, helpers
import os
from anthropic import AnthropicBedrock
import json
from dotenv import load_dotenv
load_dotenv()


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
				for key, value in data.items():
					if key != "name" and value:
						desc += f"{key}: {value}\n"
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



def request_recommendation(param): # Returns text response
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
		system=system_prompt,
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
	result = "\n".join([f"##{place['name']}\n{place['description']}" for place in places_data])

	print(result)

	return result


# request_recommendation("User rayhan, likes: urban exploration; surabaya, dislikes: sports")


# print("\n".join([f'{bruh["name"]} - {bruh["description"]}' for bruh in get_elastic_search()]))
