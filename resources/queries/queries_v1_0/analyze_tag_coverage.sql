-- Analyze tag coverage
-- Source: https://focus.finops.org/use-case/analyze-tag-coverage/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT SUM(CASE WHEN JSON_CONTAINS_PATH(tags, 'one', '$.?') THEN EffectiveCost ELSE 0 END) / SUM(EffectiveCost) * 100 AS TaggedPercentage FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? AND EffectiveCost > 0 AND ProviderName = ?