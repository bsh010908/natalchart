#!/usr/bin/env python3
"""Interactive API load test using only the Python standard library."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid


TIMEOUT = 90
ERROR_CODES = (429, 500, 502, 503, 504)


class NoRedirect(HTTPRedirectHandler):
    # Do not follow redirects that could turn a POST into a GET.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def payload(run_id, stage, index, compatibility):
    data = {
        "user_name": f"LoadTest-{stage}-{index}",
        "user_email": f"loadtest-{run_id}-{stage}-{index}@example.com",
        "user_birth_date": "1990-01-15",
        "user_birth_time": "12:00:00",
        "user_city": "Seoul",
    }
    if compatibility:
        data.update(pet_name=f"TestPet-{index}", pet_type="cat", pet_gender="female",
                    pet_breed="Mixed", pet_birth_date="2020-06-15",
                    pet_birth_time="12:00:00", pet_city="Seoul")
    return data


def request_one(base_url, run_id, stage, index, barrier):
    compatibility = index % 2 == 0
    endpoint = "/api/charts/compatibility" if compatibility else "/api/charts/humans"
    request = Request(base_url + endpoint,
                      data=json.dumps(payload(run_id, stage, index, compatibility)).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    opener = build_opener(NoRedirect())
    barrier.wait()
    started = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    start_clock = time.perf_counter()
    status = None
    error = None
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            status = response.status
            response.read()
    except HTTPError as exc:
        status = exc.code
        error = f"HTTP {status}"
        exc.close()
    except (URLError, TimeoutError, OSError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - start_clock
    return {"request": index, "endpoint": endpoint, "started_utc": started,
            "start_clock": start_clock, "status": status, "seconds": elapsed, "error": error}


def run_stage(base_url, run_id, count):
    barrier = threading.Barrier(count)
    wall_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=count) as executor:
        futures = [executor.submit(request_one, base_url, run_id, count, index, barrier)
                   for index in range(1, count + 1)]
        results = [future.result() for future in futures]
    wall_elapsed = time.perf_counter() - wall_started
    for result in results:
        print(f"#{result['request']:02d} {result['endpoint']} "
              f"start={result['started_utc']} HTTP={result['status'] or 'NO_RESPONSE'} "
              f"elapsed={result['seconds']:.3f}s"
              + (f" error={result['error']}" if result['error'] else ""))
    durations = sorted(r["seconds"] for r in results)
    successes = sum(r["status"] is not None and 200 <= r["status"] < 300 for r in results)
    codes = Counter(r["status"] for r in results)
    p95 = durations[math.ceil(0.95 * count) - 1]
    spread = max(r["start_clock"] for r in results) - min(r["start_clock"] for r in results)
    print(f"\n단계 {count}명: 성공 {successes}/{count} ({successes / count:.1%}) "
          f"평균={sum(durations) / count:.3f}s 최대={max(durations):.3f}s "
          f"p95={p95:.3f}s 전체 소요={wall_elapsed:.3f}s")
    print(f"요청 시작 시각 간격: {spread * 1000:.1f}ms")
    print("오류 집계: " + " ".join(f"{code}={codes[code]}" for code in ERROR_CODES)
          + f" NO_RESPONSE={codes[None]}")
    print("전체 HTTP 집계: " + " ".join(f"{code}={number}" for code, number in
                                         sorted(codes.items(), key=lambda pair: str(pair[0]))))
    successful_times = [r["seconds"] for r in results
                        if r["status"] is not None and 200 <= r["status"] < 300]
    if successful_times:
        print(f"성공 요청만: 평균={sum(successful_times) / len(successful_times):.3f}s "
              f"최대={max(successful_times):.3f}s")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="API 기본 URL, 예: https://api.example.com")
    parser.add_argument("--stages", nargs="+", type=int, choices=(5, 10, 20),
                        default=[5, 10, 20], help="실행 단계 (기본: 5 10 20)")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    parsed = urlsplit(base_url)
    if (parsed.scheme not in ("http", "https") or not parsed.netloc
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        parser.error("인증정보·쿼리·fragment가 없는 http(s) 기본 URL을 입력하세요.")
    if args.stages != sorted(set(args.stages)):
        parser.error("단계는 중복 없이 오름차순으로 지정하세요.")
    run_id = uuid.uuid4().hex[:12]
    print(f"대상: {base_url}\n실행 식별자: {run_id}")
    print("경고: 성공 요청의 가짜 User/Pet 데이터가 대상 DB에 저장됩니다.")
    print("실제 OpenAI 비용이 발생합니다. rate limit을 우회하거나 실패 요청을 재시도하지 않습니다.")
    print("각 단계의 응답시간 통계는 실패 요청도 포함하며 p95는 nearest-rank 방식입니다.")
    print("요청당 소켓 타임아웃은 90초입니다. 이는 전체 실행시간의 엄격한 상한은 아닙니다.\n")
    for count in args.stages:
        humans = (count + 1) // 2
        pets = count // 2
        print(f"다음 단계: {count}개 동시 요청 (사람={humans}, 궁합={pets})")
        print(f"정상 처리 시 GPT 해석 호출 {humans + 3 * pets}회, "
              f"User {count}개 / Pet {pets}개 저장 예상 (SDK 재시도 비용은 추가될 수 있음).")
        try:
            answer = input("DB 저장 및 OpenAI 비용을 확인했습니다. 실행하려면 RUN 입력: ")
        except (EOFError, KeyboardInterrupt):
            print("\n실행 취소.")
            return
        if answer.strip() != "RUN":
            print("실행 취소. 이후 단계도 실행하지 않습니다.")
            return
        run_stage(base_url, run_id, count)


if __name__ == "__main__":
    main()
