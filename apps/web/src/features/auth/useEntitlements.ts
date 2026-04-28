import { useEffect, useState } from "react";
import { AccountPlanRead, getAccountPlan } from "../../api/client";
import { useAuth } from "./AuthContext";

type EntitlementState = {
  isLoading: boolean;
  can_customize_radius: boolean;
  can_customize_max_time: boolean;
  can_customize_distance: boolean;
  max_active_metrics: number | null | undefined;
  max_listing_favorites: number | null | undefined;
  max_zone_favorites: number | null | undefined;
  zone_selection_policy: string;
  planSlug: string;
  planName: string;
  max_transit_minutes_cap: number | null;
  max_walk_minutes_cap: number | null;
  max_car_minutes_cap: number | null;
  max_zone_radius_m_cap: number | null;
  max_transport_radius_m_cap: number | null;
};

const ANONYMOUS_DEFAULTS: EntitlementState = {
  isLoading: false,
  can_customize_radius: false,
  can_customize_max_time: false,
  can_customize_distance: false,
  max_active_metrics: null,
  max_listing_favorites: 0,
  max_zone_favorites: 0,
  zone_selection_policy: "restricted",
  planSlug: "anonymous",
  planName: "Anônimo",
  max_transit_minutes_cap: null,
  max_walk_minutes_cap: null,
  max_car_minutes_cap: null,
  max_zone_radius_m_cap: null,
  max_transport_radius_m_cap: null,
};

export function useEntitlements(): EntitlementState {
  const { authStatus } = useAuth();
  const [accountPlan, setAccountPlan] = useState<AccountPlanRead | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  useEffect(() => {
    if (!authStatus.is_authenticated) {
      setAccountPlan(null);
      setHasFetched(false);
      return;
    }
    setHasFetched(false);
    getAccountPlan()
      .then((plan) => {
        setAccountPlan(plan);
        setHasFetched(true);
      })
      .catch(() => {
        setAccountPlan(null);
        setHasFetched(true);
      });
  }, [authStatus.is_authenticated]);

  if (!authStatus.is_authenticated) {
    return ANONYMOUS_DEFAULTS;
  }

  if (!hasFetched) {
    return { ...ANONYMOUS_DEFAULTS, isLoading: true };
  }

  if (!accountPlan) {
    return ANONYMOUS_DEFAULTS;
  }

  return {
    isLoading: false,
    can_customize_radius: accountPlan.entitlements.can_customize_radius,
    can_customize_max_time: accountPlan.entitlements.can_customize_max_time,
    can_customize_distance: accountPlan.entitlements.can_customize_distance,
    max_active_metrics: accountPlan.entitlements.max_active_metrics,
    max_listing_favorites: accountPlan.entitlements.max_listing_favorites,
    max_zone_favorites: accountPlan.entitlements.max_zone_favorites,
    zone_selection_policy: accountPlan.entitlements.zone_selection_policy,
    planSlug: accountPlan.plan.slug,
    planName: accountPlan.plan.name,
    max_transit_minutes_cap: accountPlan.entitlements.max_transit_minutes_cap ?? null,
    max_walk_minutes_cap: accountPlan.entitlements.max_walk_minutes_cap ?? null,
    max_car_minutes_cap: accountPlan.entitlements.max_car_minutes_cap ?? null,
    max_zone_radius_m_cap: accountPlan.entitlements.max_zone_radius_m_cap ?? null,
    max_transport_radius_m_cap: accountPlan.entitlements.max_transport_radius_m_cap ?? null,
  };
}
