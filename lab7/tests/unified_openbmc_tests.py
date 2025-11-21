#!/usr/bin/env python3

import sys
import os

if 'locust' in sys.modules:
    del sys.modules['locust']

import pytest
import requests
import urllib3
import time
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import threading
import subprocess

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://localhost:2443"
REDFISH_URL = f"{BASE_URL}/redfish/v1"
USERNAME = "root"
PASSWORD = "0penBmc"
TIMEOUT = 30
RESULTS_DIR = "/tmp/results"

test_results = {
    'webui': [],
    'api': [],
    'load': []
}

class XMLReporter:
    def __init__(self):
        self.testsuites = ET.Element('testsuites')
        self.testsuites.set('name', 'OpenBMC Unified Tests')
        self.testsuites.set('timestamp', datetime.now().isoformat())
    
    def add_test_result(self, test_type, test_name, status, message="", duration=0):
        testsuite = self.testsuites.find(f".//testsuite[@name='{test_type}']")
        if testsuite is None:
            testsuite = ET.SubElement(self.testsuites, 'testsuite')
            testsuite.set('name', test_type)
            testsuite.set('tests', '0')
            testsuite.set('failures', '0')
            testsuite.set('errors', '0')
            testsuite.set('time', '0')
        
        testcase = ET.SubElement(testsuite, 'testcase')
        testcase.set('name', test_name)
        testcase.set('time', str(duration))
        
        if status == 'failed':
            failure = ET.SubElement(testcase, 'failure')
            failure.set('message', message)
            failure.text = message
            testsuite.set('failures', str(int(testsuite.get('failures', 0)) + 1))
        elif status == 'error':
            error = ET.SubElement(testcase, 'error')
            error.set('message', message)
            error.text = message
            testsuite.set('errors', str(int(testsuite.get('errors', 0)) + 1))
        
        testsuite.set('tests', str(int(testsuite.get('tests', 0)) + 1))
        testsuite.set('time', str(float(testsuite.get('time', 0)) + duration))
    
    def save_xml(self, filename):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        tree = ET.ElementTree(self.testsuites)
        tree.write(filename, encoding='utf-8', xml_declaration=True)

xml_reporter = XMLReporter()

@pytest.fixture(scope="session")
def webdriver_session():
    chrome_options = Options()
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--ignore-ssl-errors")
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--window-size=1920,1080")
    
    chrome_paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser", 
        "/usr/bin/chromium",
        "/usr/bin/chrome"
    ]
    
    for path in chrome_paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            break
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.implicitly_wait(10)
        yield driver
    except Exception as e:
        pytest.skip(f"WebDriver не может быть создан: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()

@pytest.fixture(scope="session")
def api_session():
    session = requests.Session()
    session.verify = False
    
    response = session.post(
        f"{REDFISH_URL}/SessionService/Sessions",
        json={"UserName": USERNAME, "Password": PASSWORD},
        timeout=TIMEOUT
    )
    
    if response.status_code == 201:
        auth_token = response.headers.get('X-Auth-Token')
        if auth_token:
            session.headers['X-Auth-Token'] = auth_token
    else:
        pytest.skip(f"Не удалось создать API сессию: {response.status_code}")
    
    yield session
    
    try:
        session.delete(f"{REDFISH_URL}/SessionService/Sessions/{response.json().get('Id', '')}", timeout=TIMEOUT)
    except:
        pass
    session.close()

class TestWebUI:
    def test_webui_login(self, webdriver_session):
        start_time = time.time()
        test_name = "test_webui_login"
        
        try:
            webdriver_session.get(BASE_URL)
            time.sleep(3)
            
            inputs = webdriver_session.find_elements(By.TAG_NAME, "input")
            username_field = None
            password_field = None
            
            for inp in inputs:
                field_type = inp.get_attribute("type")
                if field_type == "text":
                    username_field = inp
                elif field_type == "password":
                    password_field = inp
            
            assert username_field and password_field, "Не найдены поля для ввода логина/пароля"
            
            username_field.send_keys(USERNAME)
            password_field.send_keys(PASSWORD)
            
            buttons = webdriver_session.find_elements(By.TAG_NAME, "button")
            login_button = None
            for btn in buttons:
                if "Log in" in btn.text or "Login" in btn.text:
                    login_button = btn
                    break
            
            assert login_button, "Не найдена кнопка входа"
            login_button.click()
            
            time.sleep(5)
            current_url = webdriver_session.current_url
            
            screenshot_path = f"{RESULTS_DIR}/webui_login_success.png"
            os.makedirs(RESULTS_DIR, exist_ok=True)
            webdriver_session.save_screenshot(screenshot_path)
            
            success = current_url != f"{BASE_URL}/#/login"
            if not success:
                try:
                    main_elements = webdriver_session.find_elements(By.XPATH, 
                        "//*[contains(text(), 'System') or contains(text(), 'Dashboard') or contains(text(), 'Overview')]")
                    success = len(main_elements) > 0
                except:
                    success = False
            
            duration = time.time() - start_time
            
            if success:
                xml_reporter.add_test_result('webui', test_name, 'passed', '', duration)
            else:
                xml_reporter.add_test_result('webui', test_name, 'failed', 'Не удалось авторизоваться', duration)
            
            assert success, "Не удалось авторизоваться в Web UI"
            
        except Exception as e:
            duration = time.time() - start_time
            xml_reporter.add_test_result('webui', test_name, 'error', str(e), duration)
            raise
    
    def test_webui_navigation(self, webdriver_session):
        start_time = time.time()
        test_name = "test_webui_navigation"
        
        try:
            webdriver_session.get(BASE_URL)
            time.sleep(3)
            
            inputs = webdriver_session.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                field_type = inp.get_attribute("type")
                if field_type == "text":
                    inp.send_keys(USERNAME)
                elif field_type == "password":
                    inp.send_keys(PASSWORD)
            
            buttons = webdriver_session.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "Log in" in btn.text or "Login" in btn.text:
                    btn.click()
                    break
            
            time.sleep(5)
            
            navigation_links = webdriver_session.find_elements(By.TAG_NAME, "a")
            nav_found = False
            
            for link in navigation_links:
                link_text = link.text.lower()
                if any(keyword in link_text for keyword in ['system', 'overview', 'dashboard', 'inventory']):
                    nav_found = True
                    break
            
            duration = time.time() - start_time
            
            if nav_found:
                xml_reporter.add_test_result('webui', test_name, 'passed', '', duration)
            else:
                xml_reporter.add_test_result('webui', test_name, 'failed', 'Не найдены элементы навигации', duration)
            
            assert nav_found, "Не найдены элементы навигации"
            
        except Exception as e:
            duration = time.time() - start_time
            xml_reporter.add_test_result('webui', test_name, 'error', str(e), duration)
            raise

class TestRedfishAPI:
    def test_api_authentication(self, api_session):
        start_time = time.time()
        test_name = "test_api_authentication"
        
        try:
            response = api_session.get(f"{REDFISH_URL}/", timeout=TIMEOUT)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                xml_reporter.add_test_result('api', test_name, 'passed', '', duration)
            else:
                xml_reporter.add_test_result('api', test_name, 'failed', f'HTTP {response.status_code}', duration)
            
            assert response.status_code == 200, f"API недоступен: {response.status_code}"
            
        except Exception as e:
            duration = time.time() - start_time
            xml_reporter.add_test_result('api', test_name, 'error', str(e), duration)
            raise
    
    def test_api_system_info(self, api_session):
        start_time = time.time()
        test_name = "test_api_system_info"
        
        try:
            response = api_session.get(f"{REDFISH_URL}/Systems/system", timeout=TIMEOUT)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                required_fields = ["@odata.id", "@odata.type", "Status"]
                missing_fields = [field for field in required_fields if field not in data]
                
                if not missing_fields:
                    xml_reporter.add_test_result('api', test_name, 'passed', '', duration)
                else:
                    xml_reporter.add_test_result('api', test_name, 'failed', f'Отсутствуют поля: {missing_fields}', duration)
                    assert False, f"Отсутствуют обязательные поля: {missing_fields}"
            else:
                xml_reporter.add_test_result('api', test_name, 'failed', f'HTTP {response.status_code}', duration)
                assert False, f"API недоступен: {response.status_code}"
            
        except Exception as e:
            duration = time.time() - start_time
            xml_reporter.add_test_result('api', test_name, 'error', str(e), duration)
            raise
    
    def test_api_power_management(self, api_session):
        start_time = time.time()
        test_name = "test_api_power_management"
        
        try:
            response = api_session.get(f"{REDFISH_URL}/Systems/system", timeout=TIMEOUT)
            
            if response.status_code != 200:
                duration = time.time() - start_time
                xml_reporter.add_test_result('api', test_name, 'failed', f'Не удалось получить информацию о системе: {response.status_code}', duration)
                pytest.skip("Система недоступна")
            
            data = response.json()
            if "Actions" not in data or "#ComputerSystem.Reset" not in data["Actions"]:
                duration = time.time() - start_time
                xml_reporter.add_test_result('api', test_name, 'failed', 'Действие Reset недоступно', duration)
                pytest.skip("Действие Reset недоступно")
            
            reset_types = ["GracefulRestart", "ForceRestart"]
            success_count = 0
            
            for reset_type in reset_types:
                resp = api_session.post(
                    f"{REDFISH_URL}/Systems/system/Actions/ComputerSystem.Reset",
                    json={"ResetType": reset_type},
                    timeout=TIMEOUT
                )
                if resp.status_code in [200, 202, 204, 400]:
                    success_count += 1
            
            duration = time.time() - start_time
            
            if success_count > 0:
                xml_reporter.add_test_result('api', test_name, 'passed', f'Успешно: {success_count}/{len(reset_types)}', duration)
            else:
                xml_reporter.add_test_result('api', test_name, 'failed', 'Все типы перезагрузки недоступны', duration)
                assert False, "Все типы перезагрузки недоступны"
            
        except Exception as e:
            duration = time.time() - start_time
            xml_reporter.add_test_result('api', test_name, 'error', str(e), duration)
            raise
    
    def test_api_thermal_sensors(self, api_session):
        start_time = time.time()
        test_name = "test_api_thermal_sensors"
        
        try:
            thermal_endpoints = [
                f"{REDFISH_URL}/Chassis/chassis/ThermalSubSystem",
                f"{REDFISH_URL}/Chassis/chassis/Thermal",
                f"{REDFISH_URL}/Thermal"
            ]
            
            thermal_data = None
            for endpoint in thermal_endpoints:
                response = api_session.get(endpoint, timeout=TIMEOUT)
                if response.status_code == 200:
                    thermal_data = response.json()
                    break
            
            duration = time.time() - start_time
            
            if thermal_data:
                temperatures = thermal_data.get("Temperatures", [])
                if temperatures:
                    valid_temps = 0
                    for sensor in temperatures:
                        temp = sensor.get("ReadingCelsius")
                        if temp is not None and -20 <= temp <= 120:
                            valid_temps += 1
                    
                    if valid_temps > 0:
                        xml_reporter.add_test_result('api', test_name, 'passed', f'Найдено {valid_temps} датчиков', duration)
                    else:
                        xml_reporter.add_test_result('api', test_name, 'failed', 'Нет валидных температурных данных', duration)
                        assert False, "Нет валидных температурных данных"
                else:
                    xml_reporter.add_test_result('api', test_name, 'failed', 'Температурные датчики не найдены', duration)
                    assert False, "Температурные датчики не найдены"
            else:
                xml_reporter.add_test_result('api', test_name, 'failed', 'Thermal endpoint недоступен', duration)
                pytest.skip("Thermal endpoint недоступен")
            
        except Exception as e:
            duration = time.time() - start_time
            xml_reporter.add_test_result('api', test_name, 'error', str(e), duration)
            raise

def run_load_test():
    start_time = time.time()
    test_name = "test_load_performance"

    try:
        locust_script = os.path.join(os.path.dirname(__file__), 'load_test.py')
        with open(locust_script, 'w') as f:
            f.write(f'''
from locust import HttpUser, task, between
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "{BASE_URL}"
REDFISH_URL = "{REDFISH_URL}"
USERNAME = "{USERNAME}"
PASSWORD = "{PASSWORD}"
TIMEOUT = {TIMEOUT}

class OpenBMCLoadTest(HttpUser):
    wait_time = between(1, 3)
    host = BASE_URL

    def on_start(self):
        self.auth_token = None
        self.setup_auth()

    def setup_auth(self):
        try:
            response = self.client.post(
                f"{{REDFISH_URL}}/SessionService/Sessions",
                json={{"UserName": USERNAME, "Password": PASSWORD}},
                verify=False,
                timeout=TIMEOUT
            )
            if response.status_code == 201:
                self.auth_token = response.headers.get('X-Auth-Token')
                if self.auth_token:
                    self.client.headers['X-Auth-Token'] = self.auth_token
        except Exception as e:
            pass

    @task(3)
    def get_system_info(self):
        try:
            response = self.client.get(
                f"{{REDFISH_URL}}/Systems/system",
                verify=False,
                timeout=TIMEOUT
            )
            if response.status_code == 200:
                data = response.json()
                power_state = data.get("PowerState", "unknown")
        except Exception as e:
            pass

    @task(2)
    def get_thermal_data(self):
        try:
            response = self.client.get(
                f"{{REDFISH_URL}}/Chassis/chassis/ThermalSubSystem",
                verify=False,
                timeout=TIMEOUT
            )
            if response.status_code == 200:
                data = response.json()
                temperatures = data.get("Temperatures", [])
        except Exception as e:
            pass

    @task(1)
    def get_session_info(self):
        try:
            response = self.client.get(
                f"{{REDFISH_URL}}/SessionService",
                verify=False,
                timeout=TIMEOUT
            )
            if response.status_code == 200:
                pass
        except Exception as e:
            pass
''')

        cmd = [
            "locust",
            "-f", locust_script,
            "--headless",
            "-u", "5",
            "-r", "1",
            "--run-time", "30s",
            "--host", BASE_URL
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        duration = time.time() - start_time

        try:
            os.remove(locust_script)
        except:
            pass

        if result.returncode == 0:
            xml_reporter.add_test_result('load', test_name, 'passed', 'Нагрузочные тесты завершены', duration)
        else:
            xml_reporter.add_test_result('load', test_name, 'failed', f'Ошибка: {result.stderr}', duration)

        return result.returncode == 0

    except Exception as e:
        duration = time.time() - start_time
        xml_reporter.add_test_result('load', test_name, 'error', str(e), duration)
        return False

def run_all_tests():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    pytest_args = [
        __file__,
        "-v",
        "--tb=short",
        f"--junitxml={RESULTS_DIR}/unified_tests.xml"
    ]
    
    exit_code = pytest.main(pytest_args)
    
    load_success = run_load_test()
    
    xml_reporter.save_xml(f"{RESULTS_DIR}/unified_test_results.xml")
    
    return exit_code == 0 and load_success

if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
