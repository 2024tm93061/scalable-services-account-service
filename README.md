# Account Service Microservice

The account service is a small microservice that manages bank accounts and enforces basic business rules (daily transfer limits, account status checks).

## Project Structure

```
account-service
├── main.py              # FastAPI application and endpoints (single-file prototype)
├── accounts.csv         # Sample account data used to seed the DB
├── requirements.txt     # Python dependencies
├── Dockerfile           # Build instructions for a container image
├── test_api.py          # Simple script to exercise the running API
└── .dockerignore        # Files to ignore when building the image
```

## Quickstart (Docker)

1. Build the image and start the service (simple Docker example):

```bash
docker build -t account-service:latest .
docker run --rm -p 8000:8000 -e DAILY_TRANSFER_LIMIT=200000 account-service:latest
```

2. Open the API docs: http://localhost:8000/docs

The service uses a local SQLite file `accounts.db` inside the container (or in your working directory when running locally). On first startup it will seed the DB from `accounts.csv` if present.

3. Test Endpoints

```bash
# from repo root, after the service is running
python test_api.py
```

## Endpoints

- **Health:** `GET /health`
- **Create Account:** `POST /accounts`
- **Read Account:** `GET /accounts/{account_id}`
- **Change Account Status:** `POST /accounts/{account_id}/status`  (payload: `{ "status": "FROZEN" }`)
- **Transfer Funds:** `POST /transfer`  (payload: `{ "from_account":1, "to_account":2, "amount":1000.50 }`)

## Sample Data

The `accounts.csv` file contains sample account rows useful for local development and testing. Typical columns included in the sample:

- account_id
- customer_id
- account_number
- account_type
- balance
- currency
- status
- created_at

## Requirements

Install the required dependencies listed in `requirements.txt` before running the application.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Notes

- The example stores a small read-optimized projection (customer_name) for demonstration; your real customer service should own and publish canonical customer data. Do not share tables across services in a multi-service architecture — replicate minimal fields as needed.