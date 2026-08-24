-- Track PEP status and sanction/media screening on client
ALTER TABLE `client`
  ADD COLUMN `is_pep` BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN `adverse_media_hits` INT NOT NULL DEFAULT 0;

-- Track jurisdiction risk level at case opening
ALTER TABLE `onboarding_case`
  ADD COLUMN `jurisdiction_risk` VARCHAR(20) DEFAULT 'LOW' COMMENT 'LOW / MEDIUM / HIGH';


  