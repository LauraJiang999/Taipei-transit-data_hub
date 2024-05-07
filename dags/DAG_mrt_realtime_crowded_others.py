import requests
import pandas as pd
import json
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta
import re
from sqlalchemy import create_engine, exc
import numpy as np
from airflow.decorators import dag, task
from zoneinfo import ZoneInfo
# 使用getenv拿取帳號密碼
load_dotenv()

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email": ["lala9456@gmail.com"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


@dag(
    dag_id="DAG_mrt_realtime_crowded_others",
    default_args=default_args,
    description="ETL MRT realtime_crowded(O,G,R line) data to mysql",
    schedule_interval="*/5 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    # Optional: Add tags for better filtering in the UI
    tags=["O", "G", "R"]
)
def DAG_mrt_crowded_others():
    @task
    def E_mrt_crowded_others():
        username = os.getenv("ANDY_USERNAME")
        password = os.getenv("ANDY_PASSWORD")
        url = "https://api.metro.taipei/metroapiex/CarWeight.asmx"  # 高運量車廂擁擠度
        headers = {
            "Content-type": "text/xml; charset=utf-8"
        }
        xmldata = f"""<?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xmlns:xsd="http://www.w3.org/2001/XMLSchema"
        xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
        <soap:Body>
        <getCarWeightByInfoEx xmlns="http://tempuri.org/">
        <userName>{username}</userName>
        <passWord>{password}</passWord>
        </getCarWeightByInfoEx>
        </soap:Body>
        </soap:Envelope>"""

        response = requests.post(url=url, headers=headers, data=xmldata)
        df = pd.DataFrame(json.loads(response.text.split("<?xml")[0]))
        print("E_mrt_crowded_others finished")
        return (df)

    @task
    def T_mrt_crowded_others(df: pd.DataFrame):

        pattern = re.compile(r"^[A-Z]+")

        def pattern_match_station_line_type(x):
            if pattern.findall(x):
                return (pattern.findall(x)[0])
            else:
                return ("")
        df["line_type"] = df["StationID"].apply(
            pattern_match_station_line_type)

        df["mrt_station_name"] = np.nan
        df = df.loc[:, ["StationID", "mrt_station_name", "line_type", "CID",
                        "Cart1L", "Cart2L", "Cart3L", "Cart4L", "Cart5L", "Cart6L", "utime"]]
        df["CID"] = df["CID"].apply(lambda x: "下行" if int(
            x) == 1 else "上行")  # 超重要  經過比對 1是下行 2是上行
        df.rename(columns={
            "StationID": "mrt_station_id",
            "StationName": "mrt_station_name",
            "CID": "direction",
            "Cart1L": "cart1",
            "Cart2L": "cart2",
            "Cart3L": "cart3",
            "Cart4L": "cart4",
            "Cart5L": "cart5",
            "Cart6L": "cart6",
            "utime": "update_time",
        }, inplace=True)
        df = df.loc[df["line_type"].isin(
            ["G", "O", "R"]),].reset_index(drop=True)
        filename = datetime.strftime(datetime.now(), "%Y-%m-%d_%H-%M-%S")
        # df.to_csv(f"./{filename}mrt_realtime_crowded_others.csv",
        #           encoding="utf-8-sig", index=False)
        # return ("OK")
        print("T_mrt_crowded_others finished")
        return (df)

    @task
    def L_mrt_crowded_others(df: pd.DataFrame):
        username_sql = os.getenv("ANDY_USERNAME_SQL")
        password_sql = os.getenv("ANDY_PASSWORD_SQL")
        server = "host.docker.internal:3306"  # docker用
        # server = "localhost:3306"
        db_name = "group2_db"
        with create_engine(f"mysql+pymysql://{username_sql}:{password_sql}@{server}/{db_name}",).connect() as conn:
            df.reset_index(drop=True, inplace=True)
            for i in range(len(df)):
                row = df.loc[[i],]
                try:
                    row.to_sql(
                        name="mrt_realtime_crowded",
                        con=conn,
                        if_exists="append",
                        index=False
                    )
                except exc.IntegrityError:
                    print("PK error :", end="")
                    print(row)
                    continue
                except Exception as e:
                    print("Error!!!!")
                    print(e)
                    continue
        print("L_mrt_crowded_others finished")
        return ("L_mrt_crowded_others finished")

    E_df = E_mrt_crowded_others()
    T_df = T_mrt_crowded_others(df=E_df)
    L_mrt_crowded_others(df=T_df)


DAG_mrt_crowded_others()