import os
import requests
import pandas as pd
import numpy as np
import qualRpy.qualR as qr
from sklearn.linear_model import LinearRegression
from datetime import datetime
from dotenv import load_dotenv
import sendgrid
from sendgrid.helpers.mail import Mail
from twilio.rest import Client

load_dotenv()  # Carrega as variáveis do .env

DATA_FOLDER = "Dados"
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

def compose_api_url(base_url, forecast_days):
    if "forecast_days" in base_url:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}forecast_days={forecast_days}"

def send_sms_alert(phone, message):
    try:
        account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        auth_token = os.environ["TWILIO_AUTH_TOKEN"]
        from_number = os.environ["TWILIO_PHONE_NUMBER"]
    except KeyError as e:
        return {"success": False, "error": f"Variável de ambiente faltando: {str(e)}"}
    
    client = Client(account_sid, auth_token)
    try:
        message_obj = client.messages.create(
            body=message,
            from_=from_number,
            to=phone
        )
        return {"success": True, "sid": message_obj.sid}
    except Exception as e:
        return {"success": False, "error": str(e)}

def send_email_alert(email, subject, message):
    SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
    FROM_EMAIL = os.environ.get("FROM_EMAIL")
    if not SENDGRID_API_KEY or not FROM_EMAIL:
        return {"success": False, "error": "Disponha de SENDGRID_API_KEY e FROM_EMAIL configurados."}
    
    try:
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        mail = Mail(from_email=FROM_EMAIL, to_emails=email, subject=subject, html_content=message)
        response = sg.send(mail)
        if response.status_code in [200, 202]:
            return {"success": True, "data": response.body}
        else:
            return {"success": False, "error": f"Status code: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def fetch_weather_data(api_url):
    try:
        response = requests.get(api_url)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        return None

def process_weather_data(json_data):
    if json_data is None:
        return None
    daily = json_data.get("daily", {})
    if not daily:
        return None
    times = daily.get("time", [])
    rain_sum = daily.get("rain_sum", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    temp_mean = daily.get("temperature_2m_mean", [])
    humidity = daily.get("relative_humidity_2m_mean", [])
    df = pd.DataFrame({
        "data": pd.to_datetime(times),
        "rain_sum": rain_sum,
        "temperature_2m_max": temp_max,
        "temperature_2m_min": temp_min,
        "temperature_2m_mean": temp_mean,
        "relative_humidity_2m_mean": humidity
    })
    return df

def forecast_storm(df):
    if df is None or df.empty:
        return "Dados insuficientes para previsão."
    next_date = df["data"].max() + pd.Timedelta(days=1)
    df["date_num"] = df["data"].apply(lambda x: x.toordinal())
    df_nonan = df.dropna(subset=["rain_sum"])
    if df_nonan.empty or len(df_nonan) < 2:
        return "Dados insuficientes para previsão."
    X = df_nonan[["date_num"]]
    y = df_nonan["rain_sum"]
    model = LinearRegression()
    model.fit(X, y)
    pred_rain = model.predict([[next_date.toordinal()]])[0]
    if pred_rain > 5:
        return f"TEMPESTADE: Previsão para {next_date.strftime('%Y-%m-%d')}: Tempestade prevista ({pred_rain:.1f} mm)."
    else:
        return f"Previsão para {next_date.strftime('%Y-%m-%d')}: Sem risco de tempestade ({pred_rain:.1f} mm)."

def update_historical_data(df_new, bairro):
    filename = os.path.join(DATA_FOLDER, f"dados_{bairro.replace(' ', '_').lower()}.csv")
    if os.path.exists(filename):
        try:
            df_history = pd.read_csv(filename, parse_dates=["data"])
            df_combined = pd.concat([df_history, df_new]).drop_duplicates(subset=["data"]).reset_index(drop=True)
        except Exception as e:
            df_combined = df_new
    else:
        df_combined = df_new
    df_combined.to_csv(filename, index=False)
    return filename, df_combined

def load_subscriptions():
    reg_file = os.path.join(DATA_FOLDER, "subscriptions.csv")
    if os.path.exists(reg_file):
        return pd.read_csv(reg_file)
    else:
        return pd.DataFrame(columns=["email", "telefone", "bairro_alerta"])

def save_subscriptions(df):
    reg_file = os.path.join(DATA_FOLDER, "subscriptions.csv")
    df.to_csv(reg_file, index=False)