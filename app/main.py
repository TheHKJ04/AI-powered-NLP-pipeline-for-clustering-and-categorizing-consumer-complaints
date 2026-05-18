# backend/main.py
from fastapi import FastAPI, Query, HTTPException, UploadFile, File, Form, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import pickle, sqlite3, re, logging, jwt
import pandas as pd
from datetime import datetime
from nltk.corpus import stopwords                #type:ignore
from nltk.stem import WordNetLemmatizer            #type:ignore
from sentence_transformers import SentenceTransformer
from prometheus_client import Counter, Histogram, generate_latest
from googletrans import Translator              #type:ignore
from passlib.context import CryptContext

app = FastAPI(title="AI Complaint Categorization System")

# Logging
logging.basicConfig(level=logging.INFO)



# Prometheus metrics
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["endpoint"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])
COMPLAINT_COUNT = Counter("complaints_total", "Total complaints", ["category"])

# NLP setup
stop_words = set(stopwords.words('english'))                    #type:ignore
lemmatizer = WordNetLemmatizer()
translator = Translator()

def preprocess(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    words = text.split()
    words = [w for w in words if w not in stop_words]
    words = [lemmatizer.lemmatize(w) for w in words]
    return " ".join(words)

# Model + DB
model = pickle.load(open("../models/model.pkl", "rb"))
cluster_names = pickle.load(open("../models/cluster_names.pkl", "rb"))
embedder = SentenceTransformer('all-MiniLM-L6-v2')

conn = sqlite3.connect("../data/complaints.db", check_same_thread=False)
c = conn.cursor()

# Complaints table
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

# Users table
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
''')
conn.commit()

# --- Auth Setup ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
SECRET_KEY = "supersecret"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password too long (max 72 characters)")
    try:
        hashed_pw = pwd_context.hash(password)
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
        return {"message": "User registered successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    user = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if user and pwd_context.verify(password, user[2]):
        token = jwt.encode({"sub": username}, SECRET_KEY, algorithm="HS256")
        return {"access_token": token}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# --- Complaint Classification ---
class ComplaintRequest(BaseModel):
    complaint: str

@app.post("/predict")
def predict_category(req: ComplaintRequest, user=Depends(verify_token)):                        #type:ignore
    REQUEST_COUNT.labels(endpoint="/predict").inc()
    with REQUEST_LATENCY.labels(endpoint="/predict").time():
        try:
            if not re.match(r'^[a-zA-Z\s]+$', req.complaint):
                req.complaint = translator.translate(req.complaint, dest="en").text    #type:ignore                   
            cleaned = preprocess(req.complaint)                                          #type:ignore
            embedding = embedder.encode([cleaned])                                            #type:ignore
            cluster = model.predict(embedding)[0]
            category = cluster_names[cluster]
            COMPLAINT_COUNT.labels(category=category).inc()

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO complaints (complaint, category, status, submitted_on, resolved_on) VALUES (?, ?, ?, ?, ?)", 
                      (req.complaint, category, "In Progress", timestamp, None))                      #type:ignore
            conn.commit()
            complaint_id = c.lastrowid  
            logging.info(f"Complaint added: {req.complaint} -> {category}")                                   #type:ignore
            return {"id": complaint_id, "category": category, "submitted_on": timestamp}                     #type:ignore
        except Exception as e:
            logging.error(f"Error in /predict: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# --- View Complaints ---
@app.get("/complaints")
def get_complaints(user=Depends(verify_token)):
    REQUEST_COUNT.labels(endpoint="/complaints").inc()
    try: 
        df = pd.read_sql_query("SELECT * FROM complaints", conn)
        if not df.empty:
            df['ComplaintID'] = df['id'].apply(lambda x: f"#C{x:03d}")
            df = df.drop(columns=["id"], errors="ignore")
        return df.to_dict(orient="records")
    except Exception as e:
        logging.error(f"Error fetching complaints: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Update Status ---
@app.put("/update_status")
def update_status(complaint_id: int, new_status: str = Query(...), user=Depends(verify_token)):
    if new_status not in ["In Progress", "Resolved"]:
        raise HTTPException(status_code=400, detail="Invalid status value")
    resolved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status == "Resolved" else None
    try:
        c.execute("UPDATE complaints SET status=?, resolved_on=? WHERE id=?", 
                  (new_status, resolved_time, complaint_id))
        conn.commit()
        logging.info(f"Complaint {complaint_id} updated to {new_status}")
        return {"message": f"Complaint {complaint_id} updated to {new_status}"}
    except Exception as e:
        logging.error(f"Error updating complaint {complaint_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Search Complaints ---
@app.get("/search")
def search_complaints(keyword: str = None, category: str = None,
                      start_date: str = None, end_date: str = None,
                      user=Depends(verify_token)):
    query = "SELECT * FROM complaints WHERE 1=1"
    params = []
    if keyword:
        query += " AND complaint LIKE ?"
        params.append(f"%{keyword}%")
    if category:
        query += " AND category=?"
        params.append(category)
    if start_date:
        query += " AND submitted_on >= ?"
        params.append(start_date)
    if end_date:
        query += " AND submitted_on <= ?"
        params.append(end_date)
    df = pd.read_sql_query(query, conn, params=params)
    if not df.empty:
        df['ComplaintID'] = df['id'].apply(lambda x: f"#C{x:03d}")
        df = df.drop(columns=["id"], errors="ignore")
    return df.to_dict(orient="records")

# --- Analytics ---
@app.get("/stats")
def stats(user=Depends(verify_token)):
    df = pd.read_sql_query("SELECT * FROM complaints", conn)
    total = len(df)
    resolved = len(df[df['status'] == "Resolved"])
    resolution_rate = (resolved / total * 100) if total > 0 else 0
    by_category = df['category'].value_counts().to_dict()
    return {
        "total_complaints": total,
        "resolution_rate": resolution_rate,
        "by_category": by_category
    }

# --- File Upload Classification ---
@app.post("/upload")
def upload_file(file: UploadFile = File(...), user=Depends(verify_token)):
    try:
        text = file.file.read().decode("utf-8", errors="ignore")
        cleaned = preprocess(text)
        embedding = embedder.encode([cleaned])
        cluster = model.predict(embedding)[0]
        category = cluster_names[cluster]

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT INTO complaints (complaint, category, status, submitted_on, resolved_on) VALUES (?, ?, ?, ?, ?)",
            (text, category, "In Progress", timestamp, None)
        )
        conn.commit()
        complaint_id = c.lastrowid

        return {
            "id": complaint_id,
            "complaint": text,
            "category": category,
            "submitted_on": timestamp
        }
    except Exception as e:
        logging.error(f"Error in /upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Health & Metrics ---
@app.get("/health")
def health_check():
    REQUEST_COUNT.labels(endpoint="/health").inc()
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    return generate_latest()
