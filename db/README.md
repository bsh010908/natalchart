# MySQL 설정

SQLAlchemy와 PyMySQL을 사용합니다. `users`와 `pets`는 `pets.user_id`로
1:N 관계를 맺습니다. 이메일은 중복을 허용하지 않으며, 반려동물이 있는
사용자는 삭제할 수 없습니다. 출생시간만 NULL을 허용합니다.
생성·수정일시는 MySQL 서버 시각으로 자동 기록합니다.

## Docker로 실행

Docker Desktop을 실행하고 프로젝트 루트에서 다음 명령을 실행합니다.
`docker-compose.yml`을 사용하며 기존 컨테이너 이름과 데이터 볼륨을 유지합니다.
`.env.example`을 참고해 `.env`에 접속 정보와 `MYSQL_ROOT_PASSWORD`를 설정합니다.
로컬에서 실행하는 API의 `MYSQL_HOST`는 `127.0.0.1`입니다.

```bash
docker compose up -d --wait mysql
docker compose ps
```

첫 실행 시 데이터베이스, 일반 사용자, `users`와 `pets` 테이블이 자동 생성됩니다.
포트는 로컬 컴퓨터에서만 접근할 수 있으며 기본값은 3309입니다.
사용 중이면 `.env`의 `MYSQL_PORT`를 3307 등으로 변경합니다.
데이터는 `natalchart_mysql_data` 볼륨에 보관되어 컨테이너를 재생성해도 유지됩니다.

```bash
# MySQL 접속 (프롬프트에 .env의 MYSQL_PASSWORD 입력)
docker compose exec mysql sh -c 'exec mysql -u "$MYSQL_USER" -p "$MYSQL_DATABASE"'
# 컨테이너 종료 (데이터 유지)
docker compose down
```

API는 로컬에서 `127.0.0.1:3309`로 연결합니다. API도 같은 Compose 네트워크의
컨테이너에서 실행한다면 API 환경변수만 `MYSQL_HOST=mysql`, `MYSQL_PORT=3306`으로
지정합니다. `.env`의 `MYSQL_PORT`는 호스트 공개 포트입니다.

초기 SQL과 계정 환경변수는 빈 데이터 볼륨에서만 적용됩니다.
기존 볼륨에 테이블이 없다면 `python -m db.database`로 생성합니다.
기존 DB의 스키마나 비밀번호 변경은 MySQL에서 별도로 적용해야 합니다.
`docker compose down -v`는 저장된 DB 데이터를 삭제하므로 주의하세요.

API를 로컬에서 실행하려면 가상환경에서 `python -m pip install -r requirements.txt`를
실행합니다. Docker가 테이블을 만들므로 `python -m db.database`는 필요하지 않습니다.
Docker 외부의 기존 MySQL을 사용하는 경우에는 이 명령으로 없는 테이블을 생성할 수 있습니다.

초기화는 없는 테이블만 생성합니다. 기존 테이블의 구조 변경은 별도 마이그레이션이
필요합니다. API에서 `Depends(get_db)`로 세션을 받고 저장 시 `session.commit()`을
호출합니다. 현재 `/api/charts`는 입력을 반환하며 DB 저장 기능은 아직 없습니다.

참고: [SQLAlchemy MySQL 문서](https://docs.sqlalchemy.org/en/20/dialects/mysql.html)
및 [MySQL Docker 이미지](https://hub.docker.com/_/mysql).
