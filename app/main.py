from fastapi import FastAPI,Query
from pydantic import BaseModel
import pickle, sqlite3, re
import pandas as pd
from datetime import datetime
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sentence_transformers import SentenceTransformer
from prometheus_client import Counter, Histogram, generate_latest

app = FastAPI(title="AI Complaint Categorization System")

# Prometheus metrics
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["endpoint"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])

stop_words = set(stopwords.words('english'))
lemmatizer = WordNetLemmatizer()

def preprocess(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    words = text.split()
    words = [w for w in words if w not in stop_words]
    words = [lemmatizer.lemmatize(w) for w in words]
    return " ".join(words)

model = pickle.load(open("../models/model.pkl", "rb"))
cluster_names = pickle.load(open("../models/cluster_names.pkl", "rb"))
embedder = SentenceTransformer('all-MiniLM-L6-v2')

conn = sqlite3.connect("../data/complaints.db", check_same_thread=False)
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint TEXT,
        category TEXT,
        status TEXT DEFAULT 'In Progress',
        submitted_on TEXT,
        resolved_on TEXT
    )
''')
conn.commit()

class ComplaintRequest(BaseModel):
    complaint: str

@app.post("/predict")
def predict_category(req: ComplaintRequest) -> dict[str,str]:
    REQUEST_COUNT.labels(endpoint="/predict").inc()
    with REQUEST_LATENCY.labels(endpoint="/predict").time():
        cleaned = preprocess(req.complaint)
        embedding = embedder.encode([cleaned])
        cluster = model.predict(embedding)[0]
        category = cluster_names[cluster]

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO complaints (complaint, category, status, submitted_on, resolved_on) VALUES (?, ?, ?, ?, ?)", 
                  (req.complaint, category, "In Progress", timestamp, None))
        conn.commit()
        return {"category": category, "submitted_on": timestamp}

@app.get("/complaints")
def get_complaints():
    REQUEST_COUNT.labels(endpoint="/complaints").inc()
    df = pd.read_sql_query("SELECT * FROM complaints", conn)
    return df.to_dict(orient="records")

@app.get("/health")
def health_check():
    REQUEST_COUNT.labels(endpoint="/health").inc()
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return generate_latest()

@app.put("/update_status")
def update_status(complaint_id: int, new_status: str = Query(...)):
    resolved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status == "Resolved" else None
    c.execute("UPDATE complaints SET status=?, resolved_on=? WHERE id=?", (new_status, resolved_time, complaint_id))
    conn.commit()
    return {"message": f"Complaint {complaint_id} updated to {new_status}"}

