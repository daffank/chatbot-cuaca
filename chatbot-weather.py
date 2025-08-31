import streamlit as st
import requests
import datetime
import pandas as pd
import altair as alt
import google.generativeai as genai
import difflib
import collections
import locale

# Terjemahan kondisi cuaca
weather_translations = {
    "clear sky": "cerah",
    "few clouds": "sedikit berawan",
    "scattered clouds": "berawan",
    "broken clouds": "sebagian berawan",
    "overcast clouds": "mendung",
    "shower rain": "hujan deras",
    "light rain": "hujan ringan",
    "moderate rain": "hujan sedang",
    "heavy intensity rain": "hujan lebat",
    "very heavy rain": "hujan sangat lebat",
    "freezing rain": "hujan membeku",
    "thunderstorm": "badai petir",
    "snow": "salju",
    "mist": "berkabut",
    "haze": "berkabut tipis",
    "fog": "kabut",
    "sand": "berpasir",
    "dust": "berdebu",
    "tornado": "angin puting beliung",
    "squalls": "angin kencang",
    "drizzle": "gerimis",
    "light intensity drizzle": "gerimis ringan",
    "heavy intensity drizzle": "gerimis lebat",
    "ragged shower rain": "hujan tidak merata",
    "partly cloudy": "berawan sebagian",
    "clouds": "berawan",
}

# Daftar kota populer
city_list = [
    "jakarta", "bandung", "semarang", "surabaya", "medan", "makassar",
    "palembang", "denpasar", "yogyakarta", "malang", "kudus"
]

# Set locale ke Indonesia untuk nama hari (jika tersedia)
try:
    locale.setlocale(locale.LC_TIME, 'id_ID.UTF-8')
except:
    pass

def get_day_name(dt):
    # Mapping manual jika locale gagal
    hari_map = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"
    }
    eng = dt.strftime("%A")
    return hari_map.get(eng, eng)

def get_weather_data(city, api_key):
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"cod": "error", "message": str(e)}

def get_forecast_data(city, api_key):
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"cod": "error", "message": str(e)}

def extract_day_from_prompt(prompt):
    prompt = prompt.lower()
    if "besok" in prompt:
        return 1
    elif "lusa" in prompt:
        return 2
    elif "beberapa hari" in prompt or "ke depan" in prompt or "forecast" in prompt:
        return "multi"
    return 0

def correct_city_name(city_name):
    city_name = city_name.lower()
    matches = difflib.get_close_matches(city_name, city_list, n=1, cutoff=0.7)
    if matches:
        return matches[0]
    return city_name

# --- Streamlit ---
st.set_page_config(page_title="Weather Chatbot", page_icon="🌦️")

with st.sidebar:
    st.title("Konfigurasi API")
    gemini_api_key = st.text_input("Masukkan Gemini API Key", type="password")
    openweathermap_api_key = st.text_input("Masukkan OpenWeatherMap API Key", type="password")

if gemini_api_key and openweathermap_api_key:
    genai.configure(api_key=gemini_api_key)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')

    st.title("Chatbot Cuaca Interaktif")
    st.caption("powered by Gemini & OpenWeatherMap")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Hai! Tanyakan saja cuaca, misalnya 'cuaca di Jakarta' atau 'perkiraan 5 hari di Bandung'."}
        ]
    if "city_history" not in st.session_state:
        st.session_state.city_history = []

    # Tampilkan riwayat obrolan
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if isinstance(msg["content"], str):
                st.markdown(msg["content"])
            else:
                if msg["content"]["type"] == "error":
                    st.error(msg["content"]["text"])
                elif msg["content"]["type"] == "image_text":
                    st.image(msg["content"]["image_url"], width=60)
                    st.markdown(msg["content"]["text"])
                elif msg["content"]["type"] == "forecast_multi":
                    st.markdown(msg["content"]["text"])
                    st.altair_chart(msg["content"]["chart"], use_container_width=True)
                    # Tampilkan detail per hari di ekspander
                    # Urutkan hari terbaru di atas
                    for hari, ringkas, detail in sorted(msg["content"]["hari_data"], reverse=True):
                        with st.expander(f"📅 {hari} — {ringkas}"):
                            cols = st.columns(len(detail))
                            for idx, d in enumerate(detail):
                                with cols[idx]:
                                    st.image(d["Icon"], width=40)
                                    st.markdown(f"**{d['Waktu']}**")
                                    st.markdown(f"{d['Suhu']}")
                                    st.markdown(f"{d['Kelembapan']}")
                                    st.markdown(f"{d['Kondisi']}")

    # Input user
    if prompt := st.chat_input("Tanyakan cuaca di kota mana saja..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        try:
            # Ambil nama kota dari Gemini
            extraction_prompt = (
                f"From the sentence '{prompt}', extract the city name only, or 'null' if none."
            )
            gemini_response = gemini_model.generate_content(extraction_prompt).text.strip()
            city_name = gemini_response if gemini_response.lower() != "null" else None

            if not city_name and st.session_state.city_history:
                city_name = st.session_state.city_history[-1]

            if city_name:
                city_name = correct_city_name(city_name)
                st.session_state.city_history.append(city_name)
                day_offset = extract_day_from_prompt(prompt)

                # --- Hari ini ---
                if day_offset == 0:
                    data = get_weather_data(city_name, openweathermap_api_key)
                    if data.get("cod") == 200:
                        temp = data["main"]["temp"]
                        desc = data["weather"][0]["description"].lower()
                        desc_id = weather_translations.get(desc, desc)
                        icon = data["weather"][0]["icon"]
                        icon_url = f"http://openweathermap.org/img/wn/{icon}@2x.png"

                        content = f"Suhu saat ini di **{city_name.capitalize()}**: **{temp}°C**, kondisi **{desc_id.capitalize()}**."
                        with st.chat_message("assistant"):
                            st.image(icon_url, width=60)
                            st.markdown(content)
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": {"type": "image_text", "text": content, "image_url": icon_url}
                        })

                # --- Forecast 5 hari ---
                elif day_offset == "multi":
                    forecast = get_forecast_data(city_name, openweathermap_api_key)
                    if str(forecast.get("cod")) == "200":
                        hourly = []
                        for item in forecast["list"]:
                            dt = datetime.datetime.utcfromtimestamp(item["dt"])
                            desc = item["weather"][0]["description"].lower()
                            icon = item["weather"][0]["icon"]
                            hourly.append({
                                "Waktu": dt,
                                "Suhu": item["main"]["temp"],
                                "Kelembapan": item["main"]["humidity"],
                                "Kondisi": weather_translations.get(desc, desc).capitalize(),
                                "Tanggal": dt.date(),
                                "Hari": f"{get_day_name(dt)}, {dt.strftime('%d %b %Y')}",
                                "Icon": f"http://openweathermap.org/img/wn/{icon}@2x.png"
                            })
                        df = pd.DataFrame(hourly)
                        if not df.empty:
                            # Grafik suhu & kelembapan
                            suhu_line = alt.Chart(df).mark_line(color="red", point=True).encode(
                                x="Waktu:T", y=alt.Y("Suhu:Q", title="Suhu (°C)", axis=alt.Axis(titleColor="red"))
                            )
                            hum_line = alt.Chart(df).mark_line(color="blue", point=True).encode(
                                x="Waktu:T", y=alt.Y("Kelembapan:Q", title="Kelembapan (%)", axis=alt.Axis(titleColor="blue"))
                            )
                            chart = alt.layer(suhu_line, hum_line).resolve_scale(y="independent")

                            hari_data = []
                            # Urutkan groupby agar hari terbaru di atas
                            for tanggal, group in sorted(df.groupby("Hari"), reverse=True):
                                avg_temp = group["Suhu"].mean()
                                common_cond = group["Kondisi"].mode()[0]
                                ringkas = f"{avg_temp:.1f}°C, {common_cond}"
                                # Ambil detail per jam
                                jam_detail = []
                                for _, row in group.iterrows():
                                    jam_detail.append({
                                        "Waktu": row["Waktu"].strftime("%H:%M"),
                                        "Suhu": f"{row['Suhu']:.2f}°C",
                                        "Kelembapan": f"{row['Kelembapan']}%",
                                        "Kondisi": row["Kondisi"],
                                        "Icon": row["Icon"]
                                    })
                                hari_data.append((tanggal, ringkas, jam_detail))

                            with st.chat_message("assistant"):
                                st.markdown(f"Berikut perkiraan cuaca di **{city_name.capitalize()}** untuk 5 hari ke depan:")
                                st.altair_chart(chart, use_container_width=True)

                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": {"type": "forecast_multi", "text": f"Berikut perkiraan cuaca di **{city_name.capitalize()}** untuk 5 hari ke depan:", "chart": chart, "hari_data": hari_data}
                            })
                        else:
                            with st.chat_message("assistant"):
                                st.error("Data perkiraan tidak tersedia.")

                # --- Besok / Lusa ---
                else:
                    forecast = get_forecast_data(city_name, openweathermap_api_key)
                    if str(forecast.get("cod")) == "200":
                        target_date = (datetime.datetime.utcnow() + datetime.timedelta(days=day_offset)).date()
                        data_hari = [i for i in forecast["list"] if datetime.datetime.utcfromtimestamp(i["dt"]).date() == target_date]
                        if data_hari:
                            avg_temp = sum(i["main"]["temp"] for i in data_hari) / len(data_hari)
                            desc_list = [i["weather"][0]["description"] for i in data_hari]
                            common_desc = collections.Counter(desc_list).most_common(1)[0][0]
                            kondisi = weather_translations.get(common_desc, common_desc).capitalize()
                            hari_str = get_day_name(datetime.datetime.combine(target_date, datetime.time()))
                            content = f"Perkiraan di **{city_name.capitalize()}** pada **{hari_str}, {target_date.strftime('%d %B %Y')}**: {avg_temp:.1f}°C, {kondisi}."
                            with st.chat_message("assistant"):
                                st.markdown(content)
                            st.session_state.messages.append({"role": "assistant", "content": content})
                        else:
                            with st.chat_message("assistant"):
                                st.error("Data perkiraan tidak tersedia untuk tanggal tersebut.")
            else:
                with st.chat_message("assistant"):
                    st.error("Maaf, saya tidak mengerti kota mana yang dimaksud.")

        except Exception as e:
            msg = "Terjadi kesalahan. Silakan coba lagi."
            if "Unauthorized" in str(e): msg = "Kunci API Anda tidak valid."
            elif "Failed to establish a new connection" in str(e): msg = "Tidak bisa terhubung ke server."
            with st.chat_message("assistant"):
                st.error(msg)
else:
    st.info("Mohon masukkan API Key di sidebar untuk mulai.")