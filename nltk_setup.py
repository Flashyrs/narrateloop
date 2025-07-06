import nltk
import os
import pickle

# Define PROJECT_ROOT relative to the current script's location.
# If this file is in 'reddit/', then PROJECT_ROOT will point to 'reddit/'.
# If this file were in 'reddit/Scripts/', PROJECT_ROOT would still point to 'reddit/'.
# This makes it portable for GitHub.
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# Define the NLTK data directory relative to PROJECT_ROOT
# This will create 'reddit/nltk_data'
NLTK_DATA_DIR = os.path.join(PROJECT_ROOT, "nltk_data")

# --- NLTK Data Download Section ---
# Make sure the NLTK data directory exists
os.makedirs(NLTK_DATA_DIR, exist_ok=True)

# Download punkt to the defined NLTK_DATA_DIR
# This downloads 'punkt' into 'reddit/nltk_data/tokenizers/punkt/english.pickle'
nltk.download("punkt", download_dir=NLTK_DATA_DIR)


# --- For Testing Tokens Section ---

# Add the custom NLTK data directory to NLTK's search path
# This is crucial for NLTK to find the downloaded data
nltk.data.path.append(NLTK_DATA_DIR)

# Explicitly construct the path to the English Punkt tokenizer pickle file
# This path is now relative to your PROJECT_ROOT, making it portable.
punkt_path = os.path.join(NLTK_DATA_DIR, "tokenizers", "punkt", "english.pickle")

# Test if the file exists before trying to open it
if not os.path.exists(punkt_path):
    print(f"Error: Punkt tokenizer file not found at {punkt_path}")
    print("Please ensure NLTK 'punkt' was downloaded correctly to the 'nltk_data' directory.")
else:
    try:
        # Load the tokenizer
        with open(punkt_path, "rb") as f:
            tokenizer = pickle.load(f)

        # Test tokenization
        text = "This is sentence one. And this is sentence two!"
        print(tokenizer.tokenize(text))

    except Exception as e:
        print(f"An error occurred during tokenizer loading or tokenization: {e}")