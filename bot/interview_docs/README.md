# HRMS Lite

HRMS Lite is a simple HR management system I built to help small teams manage employees and track attendance without the overhead of enterprise solutions. If your team just needs the basics — who's on the team, who showed up today — this covers it cleanly.

## What It Does

The app is intentionally minimal. You can add employees, view the whole team at a glance, and remove people when they leave. For attendance, you mark who's present or absent each day and can pull up history whenever you need it. There's a dashboard that gives you a quick overview of team stats, department breakdown, and recent activity, along with date filtering so you can look up attendance records across a specific range.

Validation is built in throughout — emails get checked, employee IDs have to be unique, and required fields can't be left empty.

## Tech Stack

**Frontend** — React 19 with Vite, vanilla CSS, and modern JavaScript. I kept the frontend dependencies lean on purpose.

**Backend** — FastAPI, SQLAlchemy, MySQL, and Pydantic for validation. FastAPI was the right call here; it's fast and the automatic docs are a nice bonus.

## Requirements

- Node.js 18 or higher
- Python 3.9 or higher
- MySQL 8.0 or higher

## Getting Started

### Backend Setup

Jump into the backend folder and create a virtual environment:

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file with your database details:

```env
DATABASE_URL=mysql+pymysql://root:12345678@127.0.0.1:3306/hrms_lite
FRONTEND_URL=http://localhost:5173
```

Start the server:

```bash
uvicorn main:app --reload
```

The API will be running at `http://localhost:8000`.

### Frontend Setup

Navigate to the frontend folder:

```bash
cd frontend
npm install
```

Create a `.env` file:

```env
VITE_API_URL=http://localhost:8000
```

Start the dev server:

```bash
npm run dev
```

Open `http://localhost:5173` and you're good to go.

## Sample Data

I included a SQL file with 50 employees and their attendance records for February 2026. It's a good way to get a feel for the app without having to enter data manually.

On Windows, there's a batch script:

```bash
cd backend
load_sample_data.bat
```

Or manually:

```bash
mysql -h 127.0.0.1 -P 3306 -u root -p12345678 hrms_lite < backend/sample_data.sql
```

## Configuration

### Backend

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | MySQL connection string | `mysql+pymysql://root:pass@localhost:3306/hrms_lite` |
| `FRONTEND_URL` | Frontend origin (used for CORS) | `http://localhost:5173` |

### Frontend

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_API_URL` | Backend API URL | `http://localhost:8000` |

## Deploying to Production

### Frontend — Vercel

Vercel is the easiest option for the frontend. You can either use the CLI:

```bash
npm install -g vercel
cd frontend
vercel
```

Or connect your GitHub repo through the Vercel dashboard, point it at the `frontend` folder, add `VITE_API_URL` as an environment variable, and deploy from there.

### Backend — Railway

Railway works well for the Python backend:

```bash
npm install -g @railway/cli
cd backend
railway login
railway init
railway up
```

Then add `DATABASE_URL` and `FRONTEND_URL` in the Railway dashboard. You can also do the whole thing through the dashboard if you prefer connecting your GitHub repo directly.

### Backend — Render (Alternative)

If you'd rather use Render, create a new Web Service, connect your repo, and configure it like this:

- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Add the environment variables and deploy.

## API Reference

### Employees

**Create an employee**

```http
POST /employees
Content-Type: application/json

{
  "employee_id": "EMP001",
  "name": "Priya Sharma",
  "email": "priya.sharma@company.com",
  "department": "Engineering"
}
```

Returns `201 Created` on success, `409 Conflict` if the ID already exists.

**Get all employees**

```http
GET /employees
```

Returns `200 OK` with an array of all employees.

**Delete an employee**

```http
DELETE /employees/EMP001
```

Returns `204 No Content` on success, `404 Not Found` if the employee doesn't exist.

### Attendance

**Mark attendance**

```http
POST /attendance
Content-Type: application/json

{
  "employee_id": "EMP001",
  "date": "2026-02-28",
  "status": "Present"
}
```

Returns `201 Created` on success.

**Get attendance for an employee**

```http
GET /attendance/EMP001
```

Returns `200 OK` with attendance records sorted newest first.


## Project Structure

```
hrms-lite/
├── backend/
│   ├── main.py                    # FastAPI app and all routes
│   ├── models.py                  # Database models (Employee, Attendance)
│   ├── schemas.py                 # Request/response validation
│   ├── database.py                # Database connection setup
│   ├── crud.py                    # Database operations
│   ├── sample_data.sql            # 50 employees + 1,400 attendance records
│   ├── load_sample_data.bat       # Easy data loading script
│   ├── requirements.txt           # Python packages
│   ├── test_*.py                  # Property-based tests
│   └── deployment configs         # Railway, Render, Procfile
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Main app with tab navigation
│   │   ├── components/
│   │   │   ├── Dashboard.jsx      # Overview with stats
│   │   │   ├── EmployeeList.jsx   # View all employees
│   │   │   ├── EmployeeForm.jsx   # Add new employees
│   │   │   ├── AttendanceForm.jsx # Mark attendance
│   │   │   ├── AttendanceView.jsx # View attendance records
│   │   │   └── common/            # Reusable UI components
│   │   └── services/
│   │       └── api.js             # API calls
│   ├── package.json
│   └── deployment configs         # Vercel, Netlify
│
└── README.md
```


## Assumptions and Limitations

### User and Access

The app assumes only one administrator will be using it. This was a deliberate choice to keep things simple — no login system, no user roles, no access control. It works fine for a single person managing the team, A production version would need JWT tokens, session management, and proper user authentication before you'd want to expose it externally.

### Data and Scale

The app is designed with teams of roughly 20-100 employees in mind. Performance is tuned for that scale and the architecture reflects it. If someOne is running a larger organization with 1000+ employees, then they will surely use a different approach — better indexing, pagination throughout, and possibly a more robust database setup.

All data input is assumed to be in English only.



