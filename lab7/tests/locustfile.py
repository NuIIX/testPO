from locust import HttpUser, task, between
import json


OPENBMC_HOST = "https://localhost:2443"
OPENBMC_AUTH = ("root", "0penBmc")


class OpenBMCTest(HttpUser):
    host = OPENBMC_HOST
    wait_time = between(1, 3)
    disable_known_hosts = True

    def on_start(self):
        self.client.auth = OPENBMC_AUTH
        self.client.verify = False

    @task(1)
    def get_system_info_and_power_state(self):
        """Запрос информации о системе и проверка состояния питания."""
        response = self.client.get(
            "/redfish/v1/Systems/system", name="GET /Systems/system"
        )

        response.raise_for_status()

        try:
            system_info = response.json()

            power_state = system_info.get("PowerState", "Unknown")
            print(f"System info: {response.status_code}. Power state: {power_state}")

            valid_power_states = ["On", "Off", "PoweringOn", "PoweringOff", "Unknown"]

            if power_state not in valid_power_states:

                raise Exception(
                    f"Получено недопустимое состояние питания: {power_state}"
                )

        except json.JSONDecodeError:

            raise Exception("Ошибка декодирования JSON в ответе OpenBMC.")


class WeatherTest(HttpUser):
    host = "https://wttr.in"
    wait_time = between(1, 3)

    @task(1)
    def get_novosibirsk_weather(self):
        response = self.client.get("/Novosibirsk?format=j1", name="GET /Novosibirsk")

        response.raise_for_status()

        try:
            weather_data = response.json()
            current_temp = weather_data["current_condition"][0]["temp_C"]
            print(f"Weather: {response.status_code}. Temp: {current_temp}°C")
        except (KeyError, json.JSONDecodeError) as e:

            raise Exception(f"Ошибка парсинга или структуры ответа wttr.in: {e}")


class MyLoadTest(OpenBMCTest, WeatherTest):
    pass
