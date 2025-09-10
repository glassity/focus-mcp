-- Calculate unit economics
-- Source: https://focus.finops.org/use-case/calculate-unit-economics/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT CAST(ChargePeriodStart AS DATE) AS ChargePeriodDate, SUM(BilledCost) / NULLIF(SUM(CAST(ConsumedQuantity AS DECIMAL(10, 2))), 0) AS CostPerGB FROM focus_data WHERE ChargeDescription LIKE '%transfer%' AND ConsumedUnit = 'GB' GROUP BY CAST(ChargePeriodStart AS DATE) ORDER BY ChargePeriodDate ASC;