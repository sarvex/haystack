from typing import List, Union


class Question:
    def __init__(self, text: str, uid: str = None):
        self.text = text
        self.uid = uid

    def to_dict(self):
        return {"question": self.text, "id": self.uid, "answers": []}


class QAInput:
    def __init__(self, doc_text: str, questions: Union[List[Question], Question]):
        self.doc_text = doc_text
        self.questions = [questions] if type(questions) == Question else questions

    def to_dict(self):
        questions = [q.to_dict() for q in self.questions]
        return {"qas": questions, "context": self.doc_text}
