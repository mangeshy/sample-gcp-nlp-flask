from datetime import datetime
import logging
from json2html import *
import os
import random
import pandas as pd
import numpy as np
import io
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from flask import Flask, redirect, render_template, request

from google.cloud import datastore
from google.cloud import language_v1 as language

app = Flask(__name__)


@app.route("/")
def homepage():
    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # # Use the Cloud Datastore client to fetch information from Datastore
    # Query looks for all documents of the 'Sentences' kind, which is how we
    # store them in upload_text()
    query = datastore_client.query(kind="Sentences")
    text_entities = list(query.fetch())
    query = datastore_client.query(kind="entity_analysis")
    entity_analysis = list(query.fetch())
    query = datastore_client.query(kind="entity_sentiment_analysis")
    entity_sentiment_analysis = list(query.fetch())
    mydatata = pd.DataFrame(entity_sentiment_analysis)
    new_graph_name = "graph" + str(datetime.now().time()) + ".png"
    mydatata.plot(x='magnitude', y='sentiment', kind='scatter')
    plt.savefig('templates/' + new_graph_name)

    return render_template("homepage.html", graph=new_graph_name, ext_entities=text_entities,
                           entity_analysis_list=entity_analysis, entity_sentiment_analysis=entity_sentiment_analysis)


@app.route("/upload", methods=["GET", "POST"])
def upload_text():
    text = request.form["text"]
    input_lang = request.form["language"]
    # Analyse sentiment using Sentiment API call
    sentiment = analyze_text_sentiment(text, input_lang)[0].get('sentiment score')
    entity_analysis_response = gcp_analyze_entities(text)

    # Assign a label based on the score
    overall_sentiment = 'unknown'
    if sentiment > 0:
        overall_sentiment = 'positive'
    if sentiment < 0:
        overall_sentiment = 'negative'
    if sentiment == 0:
        overall_sentiment = 'neutral'

    # Create a Cloud Datastore client.
    datastore_client = datastore.Client()

    # Fetch the current date / time.
    current_datetime = datetime.now()

    # The kind for the new entity. This is so all 'Sentences' can be queried.
    kind = "Sentences"

    # Create the Cloud Datastore key for the new entity.
    key = datastore_client.key(kind)

    # Construct the new entity using the key. Set dictionary values for entity
    entity = datastore.Entity(key)
    entity["text"] = text
    entity["lang"] = input_lang
    entity["timestamp"] = current_datetime
    entity["sentiment"] = overall_sentiment

    # Save the new entity to Datastore.
    datastore_client.put(entity)

    ## Store entity analysis
    entity_analysis_kind = "entity_analysis"

    # Create the Cloud Datastore key for the new entity.
    for entity in entity_analysis_response.entities:
        entity_analysis_key = datastore_client.key(entity_analysis_kind)
        entity_analysis = datastore.Entity(entity_analysis_key)
        entity_analysis["text"] = text
        entity_analysis["lang"] = input_lang
        entity_analysis["name"] = entity.name
        entity_analysis["type"] = language.Entity.Type(entity.type_).name
        entity_analysis["timestamp"] = current_datetime
        entity_analysis["salience"] = entity.salience
        datastore_client.put(entity_analysis)

    if input_lang == 'en':
        entity_sent_analysis_response = gcp_analyze_entity_sentiment(text, input_lang)
        ## Store entity sentiment analysis
        entity_sent_analysis_kind = "entity_sentiment_analysis"
        for entity_sent in entity_sent_analysis_response.entities:
            entity_sent_analysis_key = datastore_client.key(entity_sent_analysis_kind)
            entity_sentiment = datastore.Entity(entity_sent_analysis_key)
            calculated_sentiment = entity_sent.sentiment
            overall_sentiment = 'unknown'
            if calculated_sentiment.score > 0:
                overall_sentiment = 'positive'
            if calculated_sentiment.score < 0:
                overall_sentiment = 'negative'
            if calculated_sentiment.score == 0:
                overall_sentiment = 'neutral'
            entity_sentiment["text"] = text
            entity_sentiment["lang"] = input_lang
            entity_sentiment["name"] = entity_sent.name
            entity_sentiment["type"] = language.Entity.Type(entity.type_).name
            entity_sentiment["timestamp"] = current_datetime
            entity_sentiment["sentiment"] = overall_sentiment
            entity_sentiment["magnitude"] = calculated_sentiment.magnitude
            entity_sentiment["salience"] = entity_sent.salience
            datastore_client.put(entity_analysis)

            # Redirect to the home page.
    return redirect("/")


@app.errorhandler(500)
def server_error(e):
    logging.exception("An error occurred during a request.")
    return (
        """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(
            e
        ),
        500,
    )


def analyze_text_sentiment(text, input_lang):
    client = language.LanguageServiceClient()
    document = language.Document(content=text, type_=language.Document.Type.PLAIN_TEXT, language=input_lang)

    response = client.analyze_sentiment(document=document)

    sentiment = response.document_sentiment
    results = dict(
        text=text,
        score=f"{sentiment.score:.1%}",
        magnitude=f"{sentiment.magnitude:.1%}",
    )
    for k, v in results.items():
        print(f"{k:10}: {v}")

    # Get sentiment for all sentences in the document
    sentence_sentiment = []
    for sentence in response.sentences:
        item = {}
        item["text"] = sentence.text.content
        item["sentiment score"] = sentence.sentiment.score
        item["sentiment magnitude"] = sentence.sentiment.magnitude
        sentence_sentiment.append(item)

    return sentence_sentiment


def gcp_analyze_entities(text, debug=0):
    """
    Analyzing Entities in a String

    Args:
      text_content The text content to analyze
    """

    client = language.LanguageServiceClient()
    document = language.Document(content=text, type_=language.Document.Type.PLAIN_TEXT)
    response = client.analyze_entities(document=document)
    output = []

    # Loop through entitites returned from the API
    for entity in response.entities:
        item = {}
        item["name"] = entity.name
        item["type"] = language.Entity.Type(entity.type_).name
        item["Salience"] = entity.salience

        if debug:
            print(u"Representative name for the entity: {}".format(entity.name))

            # Get entity type, e.g. PERSON, LOCATION, ADDRESS, NUMBER, et al
            print(u"Entity type: {}".format(language.Entity.Type(entity.type_).name))

            # Get the salience score associated with the entity in the [0, 1.0] range
            print(u"Salience score: {}".format(entity.salience))

        # Loop over the metadata associated with entity. For many known entities,
        # the metadata is a Wikipedia URL (wikipedia_url) and Knowledge Graph MID (mid).
        # Some entity types may have additional metadata, e.g. ADDRESS entities
        # may have metadata for the address street_name, postal_code, et al.
        for metadata_name, metadata_value in entity.metadata.items():
            item[metadata_name] = metadata_value
            if debug:
                print(u"{}: {}".format(metadata_name, metadata_value))

        # Loop over the mentions of this entity in the input document.
        # The API currently supports proper noun mentions.
        if debug:
            for mention in entity.mentions:
                print(u"Mention text: {}".format(mention.text.content))
                # Get the mention type, e.g. PROPER for proper noun
                print(
                    u"Mention type: {}".format(language.EntityMention.Type(mention.type_).name)
                )
        output.append(item)

    # Get the language of the text, which will be the same as
    # the language specified in the request or, if not specified,
    # the automatically-detected language.
    if debug:
        print(u"Language of the text: {}".format(response.language))

    return response


def gcp_analyze_entity_sentiment(text, input_lang, debug=0):
    """
    Analyzing Entities in a String

    Args:
      text_content The text content to analyze
    """

    client = language.LanguageServiceClient()
    document = language.Document(content=text, type_=language.Document.Type.PLAIN_TEXT, language=input_lang)
    response = client.analyze_entity_sentiment(document=document)

    return response


if __name__ == "__main__":
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host="127.0.0.1", port=8085, debug=True)
