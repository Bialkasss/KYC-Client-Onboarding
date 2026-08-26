-- Adds storage for ML approval predictions + DiCE counterfactual explanations,
-- generated on: case open, document submission, document verification.
-- Prediction fields are officer/admin-only in the UI (see CaseDetailPage.jsx).
ALTER TABLE `onboarding_case`
  ADD COLUMN `ml_prediction` VARCHAR(20) NULL COMMENT 'APPROVED / REJECTED, predicted by ML model',
  ADD COLUMN `ml_approval_probability` DECIMAL(5,4) NULL COMMENT 'Predicted probability of approval, 0-1',
  ADD COLUMN `ml_recommendations` TEXT NULL COMMENT 'JSON array of DiCE counterfactual suggestions; only populated when ml_prediction = REJECTED',
  ADD COLUMN `ml_predicted_at` TIMESTAMP NULL DEFAULT NULL COMMENT 'When the prediction was last (re)computed';

CREATE INDEX idx_onboarding_case_ml_prediction ON onboarding_case (ml_prediction);
