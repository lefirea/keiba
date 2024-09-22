import sys, os
import re
from time import sleep
from pprint import pprint

import pandas as pd
import xgboost as trainer
import chromedriver_autoinstaller as chrome_inst
from xgboost import DMatrix
from selenium.common.exceptions import TimeoutException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from datetime import datetime
from bs4 import BeautifulSoup


reg = re.compile(r"芝|ダ|右|左|外|内|(2周)|(直線)|\(|\)|([0-9]回)|([0-9]日目)")


def getPopulation(url, info, driver):
    raceID = url.split("?")[1].split("&")[0].split("=")[1]
    
    try:
        driver.get(url)
    except TimeoutException:
        pass

    html = driver.page_source
    rankingBS = BeautifulSoup(html, features="lxml")

    # レース開催日を取得
    raceDay = rankingBS.body.find("div", class_="RaceChange_BtnArea").find("dd", class_="Active").find("a").text
    raceDay = raceDay.split("(")[0]
    if "/" in raceDay:
        raceDay = raceDay.replace("/", "月") + "日"
    raceDay = raceID[:4] + "年" + raceDay
    raceDay = datetime.strptime(raceDay, "%Y年%m月%d日")
    info["day"] = raceDay

    # レース場を取得
    course = rankingBS.body.find("div", class_="RaceKaisaiWrap").find("li", class_="Active").find("a").text
    info[course] = 1

    # 距離を取得
    distance = rankingBS.find("div", class_="RaceData01").find("span").text.strip()
    distance = distance.replace("m", "").replace(" ", "").split()[0]
    distance = int(reg.sub("", distance))
    info["距離"] = distance

    # 着順、馬番、単勝、人気などを取得
    table = rankingBS.body.find("table", class_="RaceTable01").find("tbody")
    trs = table.find_all("tr")
    for tr in trs:  # ヘッダー行を含めない
        tds = tr.find_all("td")
        number = int(tds[1].text.strip())  # 馬番
        odds = tds[9].find("span").text.strip()
        popular = tds[10].find("span").text.strip()

        try:
            info[number]["単勝"] = float(tds[9].find("span").text.strip())
        except:
            info[number]["単勝"] = -1.0

        try:
            info[number]["人気"] = int(tds[10].find("span").text.strip())
        except:
            info[number]["人気"] = -1

        # 性別と年齢
        sex = tds[4].text.strip()[0]
        if sex == "セ":
            sex = "牡"
        year = int(tds[4].text.strip()[1:])
        info[number][sex] = 1
        info[number]["年齢"] = year

        # 体重と増減
        weights = tds[8].text.strip()
        if weights in ["計不"] or not weights.isdigit():
            weights = "9999(9999)"
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
    
    hasiraBS = BeautifulSoup(driver.page_source, features="html.parser")
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
    chrome_inst.install()

    # selenium設定
    executable_path = "/usr/local/bin/chromedriver"
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'

    options = webdriver.ChromeOptions()
    options.add_argument('--user-agent=' + UA)
    # options.add_argument('--no-sandbox')
    # options.add_argument("--headless")
    options.add_argument('--remote-debugging-pipe')
    # options.add_argument('--disable-dev-shm-usage')

    options.add_argument("start-maximized")
    options.add_argument("enable-automation")
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-browser-side-navigation")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium-browser"

    # service = Service(executable_path=executable_path)
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(3)

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
    # f = True
    # while f:
    #     try:
    #         raceInfo = getPopulation(infoUrl.format(raceID), raceInfo, driver)
    #         f = False
    #     except TimeoutException:
    #         print("except p")
    #         sleep(1)

    raceInfo = getHasira(hasira5.format(raceID), raceInfo, driver)
    # f = True
    # while f:
    #     try:
    #         raceInfo = getHasira(hasira5.format(raceID), raceInfo, driver)
    #         f = False
    #     except TimeoutException:
    #         print("except h")
    #         sleep(1)

    driver.quit()

    return raceInfo


def predict(raceID):
    raceData = getData(raceID)
    cwd = "/home/ubuntu/keiba"

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

    table = pd.DataFrame(table, columns=columns)  # .astype(float)

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
    model.load_model(f"{cwd}/all_log.model")

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
    model.load_model(f"{cwd}/without_pop_rank_log.model")

    pred = model.predict(dx)
    pred = [(i + 1, pred[i]) for i in range(len(pred))]
    recommand2 = [x[0] for x in sorted(pred, key=lambda x: x[1], reverse=True)[:5]]

    print(",".join(map(str, recommand1)))
    print(",".join(map(str, recommand2)))


if __name__ == "__main__":
    raceID = sys.argv[1]
    predict(raceID)
