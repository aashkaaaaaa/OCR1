from flask import Flask, render_template, request, jsonify, send_from_directory
import cv2
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import os
import easyocr
from collections import Counter
import pandas as pd
from rapidfuzz import fuzz, process
import io
import base64
import json
import time

# Initialize the Flask app
app = Flask(__name__, static_folder='/tmp/results')

# Directory to save processed results
RESULT_FOLDER = '/tmp/results'
os.makedirs(RESULT_FOLDER, exist_ok=True)
app.config['RESULT_FOLDER'] = RESULT_FOLDER

# Path to the dataset CSV
CSV_FILE_PATH = "E:/Flipkart/Product.csv"  # Ensure this is correct

# Initialize EasyOCR Reader
reader = easyocr.Reader(['en'])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/capture', methods=['POST'])
def capture():
    # Get the image data from the POST request
    data = request.get_json()
    image_data = data.get('image')

    # Decode the Base64 image
    if image_data and image_data.startswith('data:image'):
        image_data = image_data.split(',')[1]
    img_bytes = base64.b64decode(image_data)
    img = Image.open(io.BytesIO(img_bytes))  # Convert bytes to PIL Image

    # Process the image for OCR and item counting
    ocr_result, processed_img_filename, match_counts = process_image(img)

    # Return the result as a JSON response
    return jsonify({
        'result': ocr_result,
        'image_url': f'/static/results/{processed_img_filename}',
        'match_counts': match_counts
    })

@app.route('/static/results/<filename>')
def serve_file(filename):
    return send_from_directory(app.config['RESULT_FOLDER'], filename)

def normalize_text(text):
    """Normalize the text for OCR and CSV matching."""
    return "".join(char for char in text.upper() if char.isalnum() or char.isspace()).strip()

def process_image(image):
    # Resize and enhance the image
    img = image.resize((800, 600), Image.LANCZOS)
    gray_img = img.convert('L')
    contrast_img = ImageEnhance.Contrast(gray_img).enhance(2.0)
    denoised_img = contrast_img.filter(ImageFilter.MedianFilter(size=3))

    # Try OCR on multiple rotations
    rotations = [0, 90, 180, 270]
    best_text = ""
    for angle in rotations:
        img_rotated = denoised_img.rotate(angle, expand=True)
        try:
            result = reader.readtext(np.array(img_rotated))
            text_from_image = " ".join([res[1] for res in result])
            if len(text_from_image) > len(best_text):
                best_text = text_from_image
        except Exception as e:
            print(f"Error in OCR at {angle}°: {e}")

    # Normalize OCR result
    normalized_text = normalize_text(best_text)
    ocr_words = normalized_text.split()

    # Load CSV data and match products
    try:
        csv_data = pd.read_csv(CSV_FILE_PATH)
        csv_products = [normalize_text(product) for product in csv_data['Product'].tolist()]
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return "Failed to load CSV", None, {}

    match_counts = {}
    for word in ocr_words:
        best_match, score, _ = process.extractOne(word, csv_products, scorer=fuzz.ratio)
        if score >= 85:
            match_counts[best_match] = match_counts.get(best_match, 0) + 1

    # Save processed image
    timestamp = int(time.time())
    processed_img_filename = f'processed_image_{timestamp}.jpg'
    processed_img_path = os.path.join(app.config['RESULT_FOLDER'], processed_img_filename)
    denoised_img.save(processed_img_path)

    return best_text if best_text else "No text found", processed_img_filename, match_counts

if __name__ == '__main__':
    app.run(debug=True)
