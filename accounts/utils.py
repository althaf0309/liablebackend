def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        # first ip in list
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

def get_user_agent(request):
    return request.META.get("HTTP_USER_AGENT", "")
