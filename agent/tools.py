from datetime import date
from uuid import uuid4
from typing import Any, Dict, List

from langchain_core.tools import tool
from pydantic import BaseModel
from psycopg2.extras import RealDictCursor

from agent.db import get_connection


class SearchPropertiesInput(BaseModel):
	location: str
	check_in: date
	check_out: date
	num_guests: int


@tool(args_schema=SearchPropertiesInput)
def search_available_properties(
	location: str, check_in: date, check_out: date, num_guests: int
) -> List[Dict[str, Any]]:
	"""Search for available properties based on location, dates, and guest count."""
	if check_out <= check_in:
		return [{"error": "check_out must be after check_in."}]

	query = """
		SELECT
			l.id,
			l.name,
			l.location,
			l.price_per_night,
			l.max_guests,
			l.amenities
		FROM listings l
		WHERE l.is_active = TRUE
			AND LOWER(l.location) = LOWER(%s)
			AND l.max_guests >= %s
			AND NOT EXISTS (
				SELECT 1
				FROM bookings b
				WHERE b.listing_id = l.id
					AND b.status = 'confirmed'
					AND b.check_in < %s
					AND b.check_out > %s
			)
		ORDER BY l.price_per_night ASC
	"""

	try:
		with get_connection() as conn:
			with conn.cursor(cursor_factory=RealDictCursor) as cur:
				cur.execute(query, (location, num_guests, check_out, check_in))
				rows = cur.fetchall()

		return [
			{
				"id": row["id"],
				"name": row["name"],
				"location": row["location"],
				"price_per_night": row["price_per_night"],
				"max_guests": row["max_guests"],
				"amenities": row.get("amenities") or [],
				"requested_check_in": str(check_in),
				"requested_check_out": str(check_out),
				"requested_guests": num_guests,
			}
			for row in rows
		]
	except Exception:
		return [{"error": "Could not search properties right now."}]


class GetListingDetailsInput(BaseModel):
	listing_id: int


@tool(args_schema=GetListingDetailsInput)
def get_listing_details(listing_id: int) -> Dict[str, Any]:
	"""Fetch full details of a specific listing by its ID."""
	query = """
		SELECT
			id,
			name,
			description,
			photos,
			house_rules,
			host_name,
			address,
			price_per_night,
			location,
			max_guests,
			amenities
		FROM listings
		WHERE id = %s AND is_active = TRUE
	"""

	try:
		with get_connection() as conn:
			with conn.cursor(cursor_factory=RealDictCursor) as cur:
				cur.execute(query, (listing_id,))
				row = cur.fetchone()

		if not row:
			return {"error": "Listing not found.", "listing_id": listing_id}

		return {
			"id": row["id"],
			"name": row["name"],
			"description": row["description"],
			"photos": row.get("photos") or [],
			"rules": row.get("house_rules") or [],
			"host_name": row["host_name"],
			"address": row["address"],
			"price_per_night": row["price_per_night"],
			"location": row["location"],
			"max_guests": row["max_guests"],
			"amenities": row.get("amenities") or [],
		}
	except Exception:
		return {"error": "Could not fetch listing details right now."}


class CreateBookingInput(BaseModel):
	listing_id: int
	guest_name: str
	guest_phone: str
	check_in: date
	check_out: date
	num_guests: int


@tool(args_schema=CreateBookingInput)
def create_booking(
	listing_id: int,
	guest_name: str,
	guest_phone: str,
	check_in: date,
	check_out: date,
	num_guests: int,
) -> Dict[str, Any]:
	"""Create a booking for a guest at a specific listing."""
	if check_out <= check_in:
		return {"error": "check_out must be after check_in."}

	if num_guests <= 0:
		return {"error": "num_guests must be greater than zero."}

	listing_query = """
		SELECT id, price_per_night, max_guests
		FROM listings
		WHERE id = %s AND is_active = TRUE
		FOR UPDATE
	"""
	overlap_query = """
		SELECT 1
		FROM bookings
		WHERE listing_id = %s
			AND status = 'confirmed'
			AND check_in < %s
			AND check_out > %s
		LIMIT 1
	"""
	insert_query = """
		INSERT INTO bookings (
			booking_code,
			listing_id,
			guest_name,
			guest_phone,
			check_in,
			check_out,
			num_guests,
			total_price_bdt,
			status
		)
		VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'confirmed')
		RETURNING id, booking_code, total_price_bdt, status
	"""

	try:
		with get_connection() as conn:
			try:
				with conn.cursor(cursor_factory=RealDictCursor) as cur:
					cur.execute(listing_query, (listing_id,))
					listing = cur.fetchone()
					if not listing:
						conn.rollback()
						return {"error": "Listing not found.", "listing_id": listing_id}

					if num_guests > listing["max_guests"]:
						conn.rollback()
						return {
							"error": "Guest count exceeds listing capacity.",
							"max_guests": listing["max_guests"],
						}

					cur.execute(overlap_query, (listing_id, check_out, check_in))
					if cur.fetchone():
						conn.rollback()
						return {
							"error": "Selected dates are no longer available for this listing.",
							"listing_id": listing_id,
						}

					nights = (check_out - check_in).days
					total_price = nights * int(listing["price_per_night"])
					booking_code = f"BK-{uuid4().hex[:8].upper()}"

					cur.execute(
						insert_query,
						(
							booking_code,
							listing_id,
							guest_name,
							guest_phone,
							check_in,
							check_out,
							num_guests,
							total_price,
						),
					)
					booking = cur.fetchone()
					conn.commit()
			except Exception:
				conn.rollback()
				raise

		return {
			"booking_id": booking["booking_code"],
			"db_booking_row_id": booking["id"],
			"listing_id": listing_id,
			"guest_name": guest_name,
			"guest_phone": guest_phone,
			"check_in": str(check_in),
			"check_out": str(check_out),
			"num_guests": num_guests,
			"status": booking["status"],
			"total_price_bdt": booking["total_price_bdt"],
		}
	except Exception:
		return {"error": "Could not create booking right now."}
