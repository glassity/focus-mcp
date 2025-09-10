-- Identify unused capacity reservations
-- Source: https://focus.finops.org/use-case/identify-unused-capacity-reservations/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, BillingAccountId, CapacityReservationId, CapacityReservationStatus, SUM(BilledCost) AS TotalBilledCost, SUM(EffectiveCost) AS TotalEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? AND ChargePeriodEnd < ? AND CapacityReservationStatus = 'Unused' GROUP BY ProviderName, BillingAccountId, CapacityReservationId, CapacityReservationStatus