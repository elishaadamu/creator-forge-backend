# Deploying Creator Forge Backend to AWS

This package contains everything needed to deploy the FastAPI backend to AWS.

---

## 🚀 Option 1: AWS App Runner (Recommended — Fastest & Easiest)
AWS App Runner provides automatic HTTPS, load balancing, health checks, and zero-maintenance container execution.

### Steps:
1. **Push your code or Docker image to AWS ECR (or connect your GitHub repo directly):**
   - In AWS Console, go to **AWS App Runner** → **Create Service**.
   - **Source:** Choose **Source code repository** (connect GitHub) OR **Container registry** (Amazon ECR).
   - If using **Source code**:
     - Runtime: `Python 3`
     - Build command: `pip install -r requirements.txt`
     - Start command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
     - Port: `8000`
   - If using **Container (Dockerfile)**:
     - The included `Dockerfile` builds and runs automatically on port 8000.
2. **Environment Variables:**
   Under **Configuration** → **Environment variables**, add the keys from `.env`:
   - `MONGODB_URI`: Your MongoDB Atlas connection string
   - `MONGODB_DB_NAME`: `creator_forge`
   - `DATABASE_URL`: Your PostgreSQL URL (Supabase or AWS RDS)
   - `SECRET_KEY`: Long random string
   - `GEMINI_API_KEY`: Your Gemini key
   - `OPENAI_API_KEY`: Your OpenAI key
   - `FRONTEND_URL`: `https://creator-forge-frontend.vercel.app`
3. Click **Create & Deploy**. App Runner will give you a default HTTPS URL (e.g. `https://xxxx.us-east-1.awsapprunner.com`).

---

## 📦 Option 2: AWS Elastic Beanstalk (Direct Zip Upload)
Elastic Beanstalk allows uploading a `.zip` archive directly in the AWS Console.

### Steps:
1. In AWS Console, open **Elastic Beanstalk** → **Create application**.
2. **Platform:** Select **Python** (Python 3.11 running on 64bit Amazon Linux 2023).
3. **Application code:** Select **Upload your code** and choose `creator-forge-backend-aws.zip`.
4. Click **Configure more options**:
   - Under **Software** → **Environment properties**, add your `.env` variables (`MONGODB_URI`, `DATABASE_URL`, etc.).
   - Under **Capacity**, select Single instance (or Load balanced if high availability needed).
5. Click **Create app**. Elastic Beanstalk will provision the EC2 instance, install packages, and launch via the included `Procfile`.

---

## 🖥️ Option 3: AWS EC2 (Single VM with Docker or Python venv)

### Using Docker:
```bash
# 1. Unzip archive on EC2
unzip creator-forge-backend-aws.zip -d creator-forge-backend
cd creator-forge-backend

# 2. Build Docker container
docker build -t creator-forge-backend .

# 3. Run container with your .env
docker run -d \
  --name creator-forge-api \
  --restart always \
  -p 80:8000 \
  --env-file .env \
  creator-forge-backend
```

### Using Systemd Service (Native Python):
```bash
sudo apt update && sudo apt install -y python3-pip python3-venv libpq-dev
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run directly or setup systemd service:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 🔍 Verification & Health Check
Once deployed, test your AWS endpoint:
```bash
curl https://<YOUR-AWS-ENDPOINT>/health
```
Expected response:
```json
{"status":"ok","app":"Creator Forge Internal Ops","version":"1.0.0"}
```
And check creators list:
```bash
curl https://<YOUR-AWS-ENDPOINT>/api/creators
```
