class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(code)


def unavailable(code="MODEL_UNAVAILABLE", message="บริการ AI ยังไม่พร้อมใช้งาน"):
    return APIError(503, code, message)


def conflict():
    return APIError(409, "STATE_CONFLICT", "สถานะรอบซ้อมเปลี่ยนไป กรุณาโหลดใหม่")
