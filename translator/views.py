from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from translator.models import Translation
from translator.serializers import TranslationSerializer
import requests
from functools import reduce
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
import os

# Create your views here.

def fetch_translation(source: str, target: str, text: str):
    # Request parameters
    token = os.environ['GEMINI_API_KEY']
    url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=' + token
    data = {
        'contents': {
            'parts': [{
                'text': f'Translate this text from {source} to {target} (only write the translation in plain text, with no sentences and no formatting): {text}'
            }]
        },
    }

    # Make the request
    response = requests.post(url, json=data)
    if response.status_code != 200:
        print(f"ERROR: Gemini API returned an error (status={response.status_code}): {response.text}")
        return Response(data={"error": "Failed to fetch translation: API returned an error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    json = response.json()

    # Parse the response, while verifying if the format is correct
    if (
        'candidates' not in json
        or len(json['candidates']) == 0
        or 'content' not in json['candidates'][0] == 0
        or 'parts' not in json['candidates'][0]['content']
        or any(map(lambda x: 'text' not in x, json['candidates'][0]['content']['parts']))
    ):
        print(f"ERROR: Gemini API returned an error (status={response.status_code}): {response.text}")
        return Response(data={"error": "Failed to fetch translation: unexpected response format"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Extract the translation, save it and return it
    translation = reduce(sum, map(lambda x: x['text'], json['candidates'][0]['content']['parts'])).strip()
    Translation.objects.create(source_language=source, target_language=target, source_text=text, target_text=translation)
    translations = Translation.objects.filter(source_language=source, target_language=target, source_text=text)
    return translations[0]

def get_translation(source: str, target: str, text: str):
    translations = Translation.objects.filter(source_language=source, target_language=target, source_text=text)
    if type(translations) is Response:
        return translations

    if translations.count() == 0:
        return None
    return translations[0]

class GenericTranslationViewSet(APIView):
    source = None
    target = None

    @swagger_auto_schema(operation_id="get_translation", manual_parameters=[openapi.Parameter('source_text', openapi.IN_QUERY, 'The text to translate', type='string', required=True)])
    def get(self, request):
        if request.query_params and 'source_text' in request.query_params:
            text = request.query_params['source_text']

            translation = get_translation(self.source, self.target, text)
            if type(translation) is Response:
                return translation

            if translation is not None:
                serializer = TranslationSerializer([translation], many=True)
                return Response(data=serializer.data, status=status.HTTP_200_OK)

            return Response(data={}, status=status.HTTP_404_NOT_FOUND)

        return Response(data={}, status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(operation_id="post_translation", manual_parameters=[openapi.Parameter('source_text', openapi.IN_QUERY, 'The text to translate', type='string', required=True)])
    def post(self, request):
        if request.query_params and 'source_text' in request.query_params:
            text = request.query_params['source_text']

            existing = get_translation(self.source, self.target, text)
            if existing is not None:
                if type(text) is Response:
                    return Response(data={}, status=status.HTTP_400_BAD_REQUEST)
                return Response(data={}, status=status.HTTP_409_CONFLICT)

            translation = fetch_translation(self.source, self.target, text)

            if type(translation) is Response:
                return translation

            if translation is not None:
                serializer = TranslationSerializer([translation], many=True)
                return Response(data=serializer.data, status=status.HTTP_200_OK)

            return Response(data={}, status=status.HTTP_404_NOT_FOUND)

        return Response(data={}, status=status.HTTP_400_BAD_REQUEST)
