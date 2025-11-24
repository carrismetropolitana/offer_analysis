from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "inputs"
OUTPUT_DIR = BASE_DIR / "outputs"

# Input
DAYTYPE_FILE = DATA_DIR / "dates.csv"

# Outputs
OUTPUT_EXCEL = OUTPUT_DIR / "output.xlsx"
OUTPUT_PLOT_RIDES = OUTPUT_DIR / "rides.png"
OUTPUT_PLOT_EXTENSIONS = OUTPUT_DIR / "extensions.png"
OUTPUT_PLOT_DAYTYPE = OUTPUT_DIR / "daytype_bar.png"

# Analysis period
START_DATE = "20250101"
END_DATE = "20251130"

# MongoDB connection
MONGO_URI = "mongodb://dgc-user:Y6cQvPEuNbfb4G3wGZ3crlduD8syT9Gxg02Nay8qkNKozrEion2YB6qWtHbl@sae-db-rs0-1-production.carrismetropolitana.pt:27017/?replicaSet=rs0"
DB_NAME = "production"
COLLECTION_NAME = "rides"

# MongoDB connection - hashed trips
#MONGO_URI = "mongodb://dgc-user:Y6cQvPEuNbfb4G3wGZ3crlduD8syT9Gxg02Nay8qkNKozrEion2YB6qWtHbl@sae-db-rs0-1-production.carrismetropolitana.pt:27017/?replicaSet=rs0"
#DB_NAME = "production"
#COLLECTION_NAME = "hashed_trips"

# MongoDB connection - stops
#MONGO_URI = "mongodb://dgc-user:Y6cQvPEuNbfb4G3wGZ3crlduD8syT9Gxg02Nay8qkNKozrEion2YB6qWtHbl@sae-db-rs0-1-production.carrismetropolitana.pt:27017/?replicaSet=rs0"
#DB_NAME = "production"
#COLLECTION_NAME = "stops"

# Optional filter
LINE_IDS = []
AGENCY_IDS = ["44"]
# Ensure outputs dir exists
OUTPUT_DIR.mkdir(exist_ok=True)




