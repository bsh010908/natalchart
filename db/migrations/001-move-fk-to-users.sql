-- 기존 DB(pets.user_id → users)를 users.pet_id → pets 구조로 바꾼다.
-- MySQL DDL은 롤백되지 않으므로 실행 전에 백업한다.
-- 전제: 모든 user가 pet을 정확히 하나 가진다(1:1).

-- 1. users.pet_id를 추가하고 기존 관계로 채운다.
ALTER TABLE users ADD COLUMN pet_id BIGINT NULL AFTER user_id;

UPDATE users u
JOIN pets p ON p.user_id = u.user_id
SET u.pet_id = p.pet_id;

-- 2. pets.user_id와 기존 FK를 제거하고 pet_id를 BIGINT로 바꾼다.
ALTER TABLE pets
    DROP FOREIGN KEY pets_ibfk_1,
    DROP INDEX user_id,
    DROP COLUMN user_id;

ALTER TABLE pets MODIFY pet_id BIGINT NOT NULL AUTO_INCREMENT;

-- 3. users.user_id를 BIGINT로 바꾸고 pet_id에 NOT NULL과 FK를 건다.
ALTER TABLE users
    MODIFY user_id BIGINT NOT NULL AUTO_INCREMENT,
    MODIFY pet_id BIGINT NOT NULL,
    ADD KEY ix_users_pet_id (pet_id),
    ADD CONSTRAINT fk_users_pet_id FOREIGN KEY (pet_id)
        REFERENCES pets (pet_id) ON DELETE RESTRICT;
