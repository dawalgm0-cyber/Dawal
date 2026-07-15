export interface DashboardSummary {
  bookings_today: number;
  bookings_by_status_today: Record<string, number>;
  active_drivers: number;
  revenue_today_gmd: string;
  revenue_month_gmd: string;
  alerts: {
    pending_verifications: number;
    open_disputes: number;
    unassigned_bookings: number;
    pending_review_bookings: number;
    pending_topups: number;
  };
}

export interface BookingListItem {
  id: number;
  rider_name: string | null;
  rider_phone: string | null;
  area_id: number | null;
  ride_type: string;
  status: string;
  priority: boolean;
  assigned_driver_id: number | null;
  created_at: string;
  posted_at: string | null;
  claimed_at: string | null;
}

export interface BookingDetail extends BookingListItem {
  pickup_lat: string | null;
  pickup_lng: string | null;
  pickup_address_text: string | null;
  destination_text: string | null;
  completed_at: string | null;
  rebook_of_booking_id: number | null;
  driver_name: string | null;
  driver_phone: string | null;
  claim_token: string | null;
  claim_used_at: string | null;
}

export interface Driver {
  id: number;
  name: string;
  phone: string;
  license_number: string | null;
  license_doc_url: string | null;
  vehicle_type: string | null;
  plate_number: string | null;
  area_id: number | null;
  verification_status: string;
  standing_tier: string;
  credit_balance: number;
  verified_at: string | null;
  created_at: string;
}

export interface Membership {
  id: number;
  driver_id: number;
  status: string;
  period_start: string;
  period_end: string;
  amount_paid: string;
  payment_reference: string | null;
}

export interface Topup {
  id: number;
  driver_id: number;
  amount_credits: number;
  amount_gmd: string;
  payment_method: string;
  reference_number: string | null;
  proof_url: string | null;
  status: string;
  created_at: string;
}

export interface MembershipRequest {
  id: number;
  driver_id: number;
  months: number;
  amount_gmd: string;
  payment_method: string;
  reference_number: string | null;
  proof_url: string | null;
  status: string;
  created_at: string;
}

export interface LedgerEntry {
  id: number;
  driver_id: number;
  transaction_type: string;
  amount_credits: number;
  amount_gmd: string | null;
  reference_number: string | null;
  payment_method: string | null;
  booking_id: number | null;
  topup_request_id: number | null;
  created_at: string;
}

export interface Dispute {
  id: number;
  booking_id: number;
  raised_by: string;
  type: string;
  description: string | null;
  status: string;
  resolution: string | null;
  resolved_by_admin_id: number | null;
  created_at: string;
  resolved_at: string | null;
}

export interface Rider {
  id: number;
  name: string;
  phone: string;
  blacklisted: boolean;
  blacklist_reason: string | null;
  fake_report_count: number;
  consent_given_at: string | null;
  created_at: string;
  booking_count?: number;
}

export interface TrendPoint { day: string; count: number; }
export interface Arpd { revenue_gmd: string; active_drivers: number; arpd_gmd: string; }
export interface Repurchase { drivers_purchased: number; drivers_repurchased: number; repurchase_rate: number; }
export interface AreaHeat { area_id: number | null; area_name: string | null; bookings: number; }

export interface ConsentLog {
  id: number; rider_id: number; booking_id: number;
  consent_type: string; consented_at: string; ip_address: string | null;
}

export interface RetentionQueue {
  cutoff: string; eligible_rider_ids: number[]; count: number;
}

export interface AuditEntry {
  id: number; admin_id: number | null; action: string;
  target_type: string | null; target_id: string | null;
  details_json: Record<string, unknown> | null; created_at: string;
}

export interface PricingConfig {
  key: string; value: string; value_type: string; updated_at: string;
}

export interface MessageTemplate {
  key: string; template_text: string; updated_at: string;
}

export interface AdminUser {
  id: number; name: string; email: string; role: string; created_at: string;
}

export interface AreaAdmin {
  id: number; name: string; center_lat: string; center_lng: string;
  radius_meters: number; captain_id: number | null;
  captain_driver_id: number | null; captain_driver_name: string | null;
}

export interface Captain {
  id: number; driver_id: number; driver_name: string | null;
  area_id: number; area_name: string | null; revenue_share_pct: string; created_at: string;
}

export interface PayoutSummary {
  captain_id: number; driver_id: number; driver_name: string | null;
  area_id: number; area_name: string | null;
  period_from: string | null; period_to: string | null;
  driver_count: number; total_purchase_gmd: string;
  revenue_share_pct: string; payout_gmd: string;
}
