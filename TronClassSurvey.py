import os
import re
import json
import base64
from random import randint
from typing import Optional, Dict

import ddddocr
import requests
from dotenv import load_dotenv

load_dotenv()
    
class TronClassSurvey:
    def __init__(self, account: str, password: str):
        self.account = account
        self.password = password

        self.token = ""
        self.user_id = ""
        self.base_url = "https://qsurvey.nfu.edu.tw/survey-api/api"
        self.api_url = f"https://qsurvey.nfu.edu.tw/survey-service/api/v1"
        self.headers = {
            "Content-Type": "application/json;charset=UTF-8"
        }

        self.login()

    def __solve_captcha(self, captcha_data: dict) -> str:
        ocr = ddddocr.DdddOcr(show_ad=False)

        image_data = captcha_data['image'][22:]
        image_data_base64 = base64.b64decode(image_data)
        captcha = ocr.classification(image_data_base64)
        return captcha
    
    def __get_cas_url(self, session: requests.Session)-> str:
        cas_response = session.get(f"{self.base_url}/cas")
        if cas_response.status_code == 200:
            cas_url = cas_response.json()
            if not cas_url:
                return ""
        else:
            return ""
        
        return cas_url

    def __verify_ticket(self, session: requests.Session, ticket: str) -> str:
        verify_response = session.get(f"{self.base_url}/users/verify/cas?ticket={ticket}")
        if verify_response.status_code != 200:
            return ""
        
        verify_data = verify_response.json()
        if not verify_data.get('token'):
            return ""

        return verify_data['token']['access_token']
    
    def set_auth_token(self, token: str):
        self.token = token
        self.headers["Authorization"] = f"Bearer {token}"
    
    def login(self) -> Optional[str]:
        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/"
        })

        cas_url = self.__get_cas_url(session)
        
        login_page = session.get(cas_url)
        login_url = re.search(r'action="(\S+)"', login_page.text).group(1).replace("&amp;", "&")

        captcha_response = session.get("https://identity.nfu.edu.tw/auth/realms/nfu/captcha/code")
        captcha_data = json.loads(captcha_response.text)
        captcha_code = self.__solve_captcha(captcha_data)
        captcha_key = captcha_data['key']

        data = {
            "username": self.account,
            "password": self.password,
            "captchaCode": captcha_code,
            "captchaKey": captcha_key,
        }

        response = session.post(url=login_url, data=data)
        
        ticket_match = re.search(r'ticket=([^&#]+)', response.url)
        if not ticket_match:
            raise Exception("login failed, ticket not found")
        
        ticket = ticket_match.group(1)
        
        token = self.__verify_ticket(session, ticket)
        
        if not token:
            raise Exception("login failed, token not found")
        
        self.set_auth_token(token)

        if self.is_login():
            return token
        else:
            return None
    
    def is_login(self) -> bool:
        response = requests.get(self.base_url + "/users/me", headers=self.headers)
        self.user_id = response.json()['id']
        return response.status_code == 200
    
    def __activate_survey(self, survey_id: str, target_ids: list) -> bool:
        try:
            requests.get(f"{self.api_url}/plan/{survey_id}", headers=self.headers)
            print(f"{self.api_url}/plan/{survey_id}")

            response = requests.post(
                url=f"{self.api_url}/surveys/{survey_id}/respondents/{self.user_id}/responses", 
                headers=self.headers, 
                json = {"targets": target_ids}
            )

            print(f"{self.api_url}/surveys/{survey_id}/respondents/{self.user_id}/responses")
            if response.status_code == 200:
                response = requests.get(f"{self.api_url}responses?survey_id={survey_id}&respondent_id={self.user_id}", headers=self.headers)
                print(f"{self.api_url}responses?survey_id={survey_id}&respondent_id={self.user_id}")
                return response.status_code == 200
            
            return False
        except Exception as e:
            return False
        
    def __get_surveys(self) -> list:
        response = requests.get(
            f"{self.api_url}/plans/me/canWrite",
            params={"user_id": self.user_id, "plan_status": "InProgress"},
            headers=self.headers
        )
        return response.json() if response.status_code == 200 else []
    
    def get_user_surveys(self) -> Dict[str, dict]:
        try:
            survey_datas = self.__get_surveys()

            activate_surveys = {}
            for data in survey_datas:
                if data['response'] is None:
                    survey_id = data['survey_id']
                    target_id = data['targets']['target_id']
                    activate_surveys.setdefault(survey_id, []).append(target_id)
            
            for survey_id, target_ids in activate_surveys.items():
                if not self.__activate_survey(survey_id, target_ids):
                    print(f"Warning: Failed to activate survey {survey_id}")
                    continue

            survey_datas = self.__get_surveys()

            surveys = {}
            for data in survey_datas:
                if data['response'] is not None:
                    surveys[data['response']['id']] = {
                        'response': data['response'],
                        'name': data['targets']['name']
                    }
            return surveys
        except Exception as e:
            return {}
    
    def __get_choice_id_by_text(self, choices: list, target_text: str, lang: str) -> Optional[str]:
        """
        Get choice ID by matching the English text.
        
        Args:
            choices (list): List of choice objects
            target_text (str): Target English text to match
            lang (str): Language of the target text (en_us, zh_tw)
            
        Returns:
            str: Matching choice ID or None if not found
        """
        for choice in choices:
            if choice.get('text', {}).get(lang, '').lower() == target_text.lower():
                return choice['id']
        return None
    
    def __process_raw_answers(self, response_questions: list, use_hard_answers: bool = False, use_high_score: bool = False) -> list:
        """
        Process raw answers into the desired format based on response questions.
        
        Args:
            response_questions (list): List of questions from the response
            use_hard_answers (bool): Whether to use hard answers instead of default answers
            use_high_score (bool): Whether to use high score answers instead of default answers
            
        Returns:
            tuple: (list of processed answers, total score)
        """
        main_answers = []

        choice = "highly agree" if use_high_score else "agree"
        choice_reverse = "highly disagree" if use_high_score else "disagree"

        study_answers = json.load(open("./study_answers.json", "r", encoding="utf-8"))

        for question in response_questions:
            question_id = question['id']
            question_number = question['question_number']
            question_type = question['type']
            question_choices = question['choices']
            question_heading = question['heading']

            answer = {
                "answer": [],
                "question_id": question_id,
                "question_number": question_number,
                "question_type": question_type,
                "score": None
            }

            if question_type == "matrix":
                matrix_score = 0

                for sub_question in question.get('sub_questions', []):
                    is_reverse = sub_question['options'].get('reverse_scoring', False)
                    choice_id = self.__get_choice_id_by_text(
                        question_choices, 
                        choice if not is_reverse else choice_reverse,
                        'en_us'
                    )
                    score = 5 if use_high_score else 4

                    sub_answer = {
                        "answer": choice_id,
                        "question_id": sub_question['id'],
                        "score": score,
                        "question_type": "single_selection",
                        "question_number": sub_question['question_number'],
                        "reverse_scoring": is_reverse
                    }
                    answer["answer"].append(sub_answer)
                    matrix_score += score

                answer["score"] = matrix_score
                main_answers.append(answer)
                continue

            elif question_type == "single_selection":
                question_title = question_heading['text']['default']
                if question_title in study_answers:
                    target_text = study_answers[question_title]["hard" if use_hard_answers else "default"]
                    choice_id = self.__get_choice_id_by_text(question_choices, target_text, 'zh_tw')
                    if choice_id:
                        answer['answer'].append(choice_id)
                main_answers.append(answer)
                continue

            elif question_type == "multi_selection":
                question_title = question_heading['text']['default']
                if question_title in study_answers:
                    targets = study_answers[question_title]["hard" if use_hard_answers else "default"]
                    for target_text in targets:
                        choice_id = self.__get_choice_id_by_text(question_choices, target_text, 'zh_tw')
                        if choice_id:
                            answer['answer'].append(choice_id)
                main_answers.append(answer)
                continue

            elif question_type == "short_answer":
                main_answers.append(answer)
                continue

        return main_answers

    def __process_answers(self, raw_answers: dict, response: dict, use_hard_answers: bool = False, use_high_score: bool = False) -> dict:
        """
        Update raw answers with processed answers.
        
        Args:
            raw_answers (dict): Original raw answers dictionary
            response (dict): Response containing questions
            use_hard_answers (bool): Whether to use hard answers
            use_high_score (bool): Whether to use high score answers
            
        Returns:
            dict: Updated raw answers with processed answers
        """
        processed = raw_answers.copy()
        answers = self.__process_raw_answers(response['questions'], use_hard_answers, use_high_score)

        write_time = randint(30, 500)

        processed['answers'] = answers
        processed['status'] = 'SUBMITTED'
        processed['write_time'] = write_time

        return processed
    
    def answer_survey(self, survey_id: str, answers: dict) -> bool:
        try:
            response = requests.put(
                f"{self.api_url}/responses/{survey_id}", 
                headers={
                    **self.headers,
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "zh-TW,zh;q=0.9,en;q=0.8",
                    "cache-control": "no-cache",
                    "pragma": "no-cache"
                },
                json=answers
            )
            return response.status_code == 200
        except Exception as e:
            return False

    def process_user_survey(self, use_hard_answers: bool = False, use_high_score: bool = False):
        """
        Process user surveys and answer them.

        Args:
            use_hard_answers (bool): Whether to use hard answers
            use_high_score (bool): Whether to use high score answers

        Returns:
            None
        """
        surveys = self.get_user_surveys()

        for survey_id, survey_data in surveys.items():
            requests.get(f"{self.api_url}/responses/{survey_id}", headers=self.headers)
            response = requests.get(f"{self.api_url}/surveys/{survey_data['response']['survey_id']}", headers=self.headers)
            answers = self.__process_answers(survey_data['response'], response.json(), use_hard_answers, use_high_score)

            status = self.answer_survey(survey_id, answers)
            if status:
                print(f"Survey {survey_data['name']} answered successfully!")
            else:
                print(f"Survey {survey_data['name']} failed to answer.")

if __name__ == "__main__":
    account = os.getenv('ACCOUNT')
    password = os.getenv('PASSWORD')
    t = TronClassSurvey(account, password)
    t.process_user_survey(False, False)