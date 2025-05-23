import streamlit as st
from backend import (
    compose_api_url, fetch_weather_data, process_weather_data, forecast_storm,
    update_historical_data, load_subscriptions, save_subscriptions,
    send_sms_alert, send_email_alert
)
from streamlit_autorefresh import st_autorefresh
import os
from datetime import datetime
import pandas as pd

# Atualização automática a cada 24 horas
st_autorefresh(interval=86400000, key="datarefresh")

neighborhoods = {
    "Capão Redondo": os.environ.get("API_CAPAO_REDONDO"),
    "Guarapiranga": os.environ.get("API_GUARAPIRANGA"),
    "Jardim Angela": os.environ.get("API_JARDIM_ANGELA"),
    "Jardim São Luis": os.environ.get("API_JARDIM_SAO_LUIS"),
    "Jardim Irene": os.environ.get("API_JARDIM_IRENE")
}

# Formulário público de inscrição para alertas de tempestade
st.sidebar.subheader("Inscreva-se para Alertas de Tempestade")
with st.sidebar.form("form_subscription"):
    sub_email = st.text_input("E-mail")
    sub_phone = st.text_input("Telefone (com DDD, ex: +11999999999)")
    sub_bairro = st.selectbox("Bairro para receber alerta", list(neighborhoods.keys()))
    submit_sub = st.form_submit_button("Inscrever")
if submit_sub:
    subs_df = load_subscriptions()
    if sub_email in subs_df["email"].values:
        st.sidebar.info("Você já está inscrito.")
    else:
        nova_insc = pd.DataFrame([{"email": sub_email, "telefone": sub_phone, "bairro_alerta": sub_bairro}])
        subs_df = pd.concat([subs_df, nova_insc], ignore_index=True)
        save_subscriptions(subs_df)
        st.sidebar.success("Inscrição realizada com sucesso!")

# Página principal
st.title("Previsão Meteorológica, Histórico e Alerta de Tempestade via SMS e E-mail")
st.markdown(
    "O sistema coleta dados diários da API QUALAR-CETESB para os seguintes bairros adjacentes:\n"
    "**Capão Redondo**, **Guarapiranga**, **Jardim Angela**, **Jardim São Luis** e **Jardim Irene**.\n"
    "Os dados são atualizados diariamente e exibidos em gráficos históricos.\n"
    "A IA prevê tempestades; se a previsão indicar tempestade, um alerta será enviado via SMS e e‑mail para os inscritos."
)

forecast_period = st.selectbox(
    "Selecione o horizonte de previsão", 
    ("1", "3", "7"), 
    format_func=lambda x: f"{x} dia{'s' if x != '1' else ''}"
)

bairro_consulta = st.selectbox("Selecione o Bairro para consulta dos dados", list(neighborhoods.keys()))
base_api_url = neighborhoods[bairro_consulta]
api_url = compose_api_url(base_api_url, forecast_period)

json_data = fetch_weather_data(api_url)
df_weather = process_weather_data(json_data)

if df_weather is not None:
    csv_filename, df_history = update_historical_data(df_weather, bairro_consulta)
    st.success("Dados atualizados com sucesso!")
    st.write("Última atualização:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    st.subheader("Previsão de Tempestade (IA)")
    storm_forecast = forecast_storm(df_weather)
    st.info(storm_forecast)
    
    if "TEMPESTADE" in storm_forecast:
        subs_df = load_subscriptions()
        target_subs = subs_df[subs_df["bairro_alerta"] == bairro_consulta]
        if not target_subs.empty:
            for idx, row in target_subs.iterrows():
                phone = row["telefone"]
                email = row["email"]
                sms_response = send_sms_alert(phone, f"Alerta de Tempestade: {storm_forecast}")
                if sms_response.get("success"):
                    st.write(f"Alerta SMS enviado para {email} com sucesso!")
                else:
                    st.write(f"Erro ao enviar SMS para {email}: {sms_response.get('error')}")
                email_response = send_email_alert(email, "Alerta de Tempestade", f"<strong>Alerta:</strong> {storm_forecast}")
                if email_response.get("success"):
                    st.write(f"E-mail de alerta enviado para {email} com sucesso!")
                else:
                    st.write(f"Erro ao enviar e-mail para {email}: {email_response.get('error')}")
        else:
            st.info("Nenhuma inscrição para alertas neste bairro.")
    
    st.subheader("Histórico dos Parâmetros")
    df_chart = df_history.copy().set_index("data")
    st.markdown("**Temperatura Máx (°C)**")
    st.line_chart(df_chart["temperature_2m_max"])
    st.markdown("**Temperatura Mín (°C)**")
    st.line_chart(df_chart["temperature_2m_min"])
    st.markdown("**Soma de Chuva (mm)**")
    st.line_chart(df_chart["rain_sum"])
    st.markdown("**Umidade Média (%)**")
    st.line_chart(df_chart["relative_humidity_2m_mean"])
    
    csv_data = df_history.to_csv(index=False).encode("utf-8")
    st.download_button("Baixar CSV Histórico", data=csv_data, file_name=csv_filename, mime="text/csv")
else:
    st.error("Não foi possível obter dados da API.")