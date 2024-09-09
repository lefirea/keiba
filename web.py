import sys, os
import re
from time import sleep, time

import numpy as np
import pandas as pd
import xgboost as trainer
from xgboost import DMatrix
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, jsonify, send_file

reg = re.compile(r"[芝ダ\s右左外内(2周)(直線)]")
app = Flask(__name__)


@app.route("/", methods=["GET"])
def test():
    return render_template("index.html")


@app.route("/predict", methods=["POST"])
def predict():
    raceID = request.form["raceID"]
    raceData = getData(raceID)

    columns = [
        "馬番",
        "単勝", "人気",
        "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉",
        "距離",
        "牡", "牝",
        "年齢",
        "馬体重",
        "増減",
        "前走からの日数",
        "前走順位",
        "2走順位",
        "3走順位",
        "4走順位",
        "5走順位"
    ]

    table = []
    for i in range(1, 19):
        odds = raceData[i]["単勝"]
        if odds == 0:
            continue

        row = []
        row.append(i)  # 馬番

        row.append(raceData[i]["単勝"])
        row.append(raceData[i]["人気"])

        row.append(raceData["札幌"])
        row.append(raceData["函館"])
        row.append(raceData["福島"])
        row.append(raceData["新潟"])
        row.append(raceData["東京"])
        row.append(raceData["中山"])
        row.append(raceData["中京"])
        row.append(raceData["京都"])
        row.append(raceData["阪神"])
        row.append(raceData["小倉"])
        row.append(raceData["距離"])

        row.append(raceData[i]["牡"])
        row.append(raceData[i]["牝"])

        row.append(raceData[i]["年齢"])
        row.append(raceData[i]["馬体重"])
        row.append(raceData[i]["増減"])

        row.append(raceData[i]["前走からの日数"])
        row.append(raceData[i]["前走順位"])
        row.append(raceData[i]["2走順位"])
        row.append(raceData[i]["3走順位"])
        row.append(raceData[i]["4走順位"])
        row.append(raceData[i]["5走順位"])

        table.append(row)

    table = pd.DataFrame(table, columns=columns)#.astype(float)

    columns = [
        # "着順",
        "馬番",
        "単勝", "人気",
        "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉",
        "距離",
        "牡", "牝",
        "年齢",
        "馬体重",
        "増減",
        "前走からの日数",
        "前走順位",
        "2走順位",
        "3走順位",
        "4走順位",
        "5走順位"
    ]
    params = {
        # "num_class": 2,
        "max_depth": 2,
        "objective": "binary:logistic",
        "nthread": 4,
        "eta": 1e-2
    }
    dx = DMatrix(table[columns])
    model = trainer.Booster(params)
    model.load_model("all_log.model")

    pred = model.predict(dx)
    pred = [(i + 1, pred[i]) for i in range(len(pred))]
    recommand1 = [x[0] for x in sorted(pred, key=lambda x: x[1], reverse=True)[:5]]

    columns = [
        # "着順",
        "馬番",
        # "単勝", "人気",
        "札幌", "函館", "福島", "新潟", "東京", "中山", "中京", "京都", "阪神", "小倉",
        "距離",
        "牡", "牝",
        "年齢",
        "馬体重",
        "増減",
        "前走からの日数",
        # "前走順位",
        # "2走順位",
        # "3走順位",
        # "4走順位",
        # "5走順位"
    ]
    dx = DMatrix(table[columns])
    model = trainer.Booster(params)
    model.load_model("without_pop_rank_log.model")

    pred = model.predict(dx)
    pred = [(i + 1, pred[i]) for i in range(len(pred))]
    recommand2 = [x[0] for x in sorted(pred, key=lambda x: x[1], reverse=True)[:5]]

    ret = {"result1": recommand1,
           "result2": recommand2}
    return jsonify(ret)


def getPopulation(url, info, driver):
    raceID = url.split("?")[1].split("&")[0].split("=")[1]

    try:
        driver.get(url)
    except TimeoutException:
        pass
    sleep(1)

    html = driver.page_source
    rankingBS = BeautifulSoup(html, features="lxml")

    # レース開催日を取得
    raceDay = rankingBS.body.find("div", class_="data_intro").find("p", class_="smalltxt").text
    raceDay = raceDay.split(" ")[0]
    raceDay = datetime.strptime(raceDay, "%Y年%m月%d日")
    info["day"] = raceDay

    # レース場を取得
    course = rankingBS.body.find("div", class_="data_intro").find("p", class_="smalltxt").text
    course = course.split()[1]
    course = reg.sub("", course)
    info[course] = 1

    # 距離を取得
    distance = rankingBS.find("dl", class_="racedata fc").find("span").text
    distance = distance.replace("m", "").replace(" ", "").split()[0]
    distance = int(reg.sub("", distance))
    info["距離"] = distance

    # 着順、馬番、単勝、人気などを取得
    table = rankingBS.body.find("table", class_="race_table_01").find("tbody")
    trs = table.find_all("tr")
    for tr in trs[1:]:  # ヘッダー行を含めない
        tds = tr.find_all("td")
        rank = tds[0].text.strip()
        number = int(tds[2].text.strip())  # 馬番
        if rank.isdigit():
            info[number]["着順"] = int(rank)
            info[number]["単勝"] = float(tds[12].text.strip())
            info[number]["人気"] = int(tds[13].find("span").text.strip())
        else:
            info[number]["着順"] = 0
            info[number]["単勝"] = 0
            info[number]["人気"] = 0

        # 性別と年齢
        sex = tds[4].text.strip()[0]
        if sex == "セ":
            sex = "牡"
        year = int(tds[4].text.strip()[1:])
        info[number][sex] = 1
        info[number]["年齢"] = year

        # 体重と増減
        weights = tds[14].text.strip()
        if weights in ["計不"] or weights == "" or weights == "--":
            weights = "-1(0)"
        info[number]["馬体重"] = int(weights.split("(")[0])

        if weights[-1] == ")":
            gain = weights.split("(")[1].replace(")", "")
            if gain.isdigit():
                info[number]["増減"] = int(gain)
            else:
                info[number]["増減"] = 0
        else:
            info[number]["増減"] = 0

    del rankingBS, raceDay  # メモリリーク対策

    return info


def getHasira(url, info, driver):
    hasiraTitle = ["前走順位", "2走順位", "3走順位", "4走順位", "5走順位"]

    try:
        driver.get(url)
    except TimeoutException:
        pass
    sleep(1)

    html = driver.page_source

    # 表以前の部分を削除
    p = html.find("<table class=\"Shutuba_Table Shutuba_Past5_Table tablesorter")
    trimHTML = html[:p]
    trimHTML = "<html><head><meta charset='utf-8'></meta></head><body><div><div><div><div>" + trimHTML

    # 表以降の部分を削除
    p = trimHTML.find("<div style=\"display:none;\" id=\"free_odds_limit_overlay\">")
    trimHTML = trimHTML[p:]

    hasiraBS = BeautifulSoup(driver.page_source, features="lxml")
    body = hasiraBS.body
    table = body.find("table", class_="Shutuba_Past5_Table").find("tbody")

    trs = table.find_all("tr")
    for tr in trs:
        tds = tr.find_all("td")
        number = int(tds[1].text)
        zenso = tds[5:10]
        for i in range(5):
            if zenso[i].get("class")[0] == "Past":
                data = zenso[i].find("div", class_="Data_Item")
                data1 = data.find("div", class_="Data01")
                data1Span = data1.find_all("span")
                lastDay = data1Span[0].text.split(" ")[0]
                data1Rank = data1Span[1].text
                data1Rank = int(data1Rank) if data1Rank.isdigit() else 0
                info[number][hasiraTitle[i]] = data1Rank
                del data, data1, data1Span, data1Rank  # メモリリーク対策

                # 前走からの経過日数を計算
                if i == 0:
                    lastDay = datetime.strptime(lastDay, "%Y.%m.%d")
                    dd = info["day"] - lastDay
                    info[number]["前走からの日数"] = dd.days
                    del lastDay, dd  # メモリリーク対策

    # メモリリーク対策に、不要なものは削除
    del number, trs, tds, zenso
    del hasiraBS, body, table

    return info


def getData(raceID):
    # selenium設定
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(5)

    infoUrl = "https://race.netkeiba.com/race/shutuba.html?race_id={}&rf=race_submenu"
    hasira5 = "https://race.netkeiba.com/race/shutuba_past.html?race_id={}&rf=shutuba_submenu"

    raceInfo = {"day": "",
                # "良": 0, "稍重": 0, "重": 0, "不良": 0,
                "札幌": 0, "函館": 0, "福島": 0,
                "新潟": 0, "東京": 0, "中山": 0,
                "中京": 0, "京都": 0, "阪神": 0, "小倉": 0,
                "距離": 0,
                }
    for i in range(1, 19):
        raceInfo[i] = {
            "着順": 0,
            "単勝": 0.0,
            "人気": 0,
            "牡": 0,
            "牝": 0,
            "年齢": 0,
            "馬体重": 0,
            "増減": 0,
            "前走からの日数": 0,
            "前走順位": 0,
            "2走順位": 0,
            "3走順位": 0,
            "4走順位": 0,
            "5走順位": 0
        }

    raceInfo = getPopulation(infoUrl.format(raceID), raceInfo, driver)
    raceInfo = getHasira(hasira5.format(raceID), raceInfo, driver)

    driver.close()

    return raceInfo


if __name__ == "__main__":
    app.run()
