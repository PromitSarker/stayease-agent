from datetime import date
from uuid import uuid4
from typing import Any, Dict, List, Union

from langchain_core.tools import tool
from pydantic import BaseModel, field_validator
from psycopg2.extras import RealDictCursor

from agent.db import get_connection


class SearchPropertiesInput(BaseModel):
	location: str
	check_in: date
	check_out: date
	num_guests: Union[int, str]

	@field_validator("num_guests", mode="before")
	@classmethod
	def coerce_num_guests(cls, v: Any) -> int:
		try:
			return int(v)
		except (ValueError, TypeError) as exc:
			raise ValueError(f"num_guests must be an integer, got {v!r}") from exc


@tool(args_schema=SearchPropertiesInput)
def search_available_properties(
	location: str, check_in: date, check_out: date, num_guests: int
) -> str:
	"""
	Search for available properties based on location, dates, and guest count.
	
	Why it's needed: The AI doesn't know what properties actually exist in the database. 
	It uses this tool to ask the database to find open rooms that don't have overlapping bookings.
	"""
	if check_out <= check_in:
		return "ERROR: check_out must be after check_in."

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

		if not rows:
			return f"NO_RESULTS: Sorry, we currently have no listings in '{location}' for {num_guests} guest(s) on those dates."

		output = f"Found {len(rows)} properties in {location}:\n"
		for row in rows:
			output += f"- ID: {row['id']} | {row['name']} | Price: {row['price_per_night']} BDT/night | Max Guests: {row['max_guests']}\n"
		return output
	except Exception as e:
		return f"ERROR: Could not search properties right now: {str(e)}"


class GetListingDetailsInput(BaseModel):
	listing_id: Union[int, str]

	@field_validator("listing_id", mode="before")
	@classmethod
	def coerce_listing_id(cls, v: Any) -> int:
		try:
			return int(v)
		except (ValueError, TypeError) as exc:
			raise ValueError(f"listing_id must be an integer, got {v!r}") from exc


@tool(args_schema=GetListingDetailsInput)
def get_listing_details(listing_id: int) -> str:
	"""
	Fetch full details of a specific listing by its ID.
	
	Why it's needed: After the user sees search results, they might want more info 
	(like rules, exact address, or amenities) before they commit to booking. 
	This tool grabs that specific deep-dive information for exactly one property.
	"""
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
			return f"ERROR: Listing with ID '{listing_id}' not found."

		output = f"Details for '{row['name']}' (ID: {listing_id}):\n"
		output += f"- Location: {row['location']}\n"
		output += f"- Address: {row['address']}\n"
		output += f"- Price: {row['price_per_night']} BDT/night\n"
		output += f"- Max Guests: {row['max_guests']}\n"
		output += f"- Host: {row['host_name']}\n"
		output += f"- Description: {row['description']}\n"
		if row.get('amenities'):
			output += f"- Amenities: {', '.join(row['amenities'])}\n"
		return output
	except Exception as e:
		return f"ERROR: Could not fetch listing details: {str(e)}"


class CreateBookingInput(BaseModel):
	listing_id: Union[int, str]
	guest_name: str
	guest_phone: str
	check_in: date
	check_out: date
	num_guests: Union[int, str]

	@field_validator("listing_id", "num_guests", mode="before")
	@classmethod
	def coerce_int_fields(cls, v: Any) -> int:
		try:
			return int(v)
		except (ValueError, TypeError) as exc:
			raise ValueError(f"Expected an integer, got {v!r}") from exc


@tool(args_schema=CreateBookingInput)
def create_booking(
	listing_id: int,
	guest_name: str,
	guest_phone: str,
	check_in: date,
	check_out: date,
	num_guests: int,
) -> str:
	"""
	Create a booking for a guest at a specific listing.
	
	Why it's needed: Allows the LLM to safely write data into our database to finalize an order. 
	It first double-checks if the room is still open (in case someone else booked it inside the last minute)
	and then saves the reservation details and generates a tracking ID.
	"""
	if check_out <= check_in:
		return "ERROR: check_out must be after check_in."

	if num_guests <= 0:
		return "ERROR: num_guests must be greater than zero."

	listing_query = """
		SELECT name, price_per_night, max_guests
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
						return f"ERROR: Listing with ID '{listing_id}' not found."

					if num_guests > listing["max_guests"]:
						conn.rollback()
						return f"ERROR: Guest count ({num_guests}) exceeds listing capacity ({listing['max_guests']})."

					cur.execute(overlap_query, (listing_id, check_out, check_in))
					if cur.fetchone():
						conn.rollback()
						return "ERROR: Selected dates are no longer available for this listing."

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
			except Exception as e:
				conn.rollback()
				return f"ERROR: Internal database failure: {str(e)}"

		output = f"Booking confirmed for '{listing['name']}'!\n"
		output += f"- Booking Code: {booking['booking_code']}\n"
		output += f"- Guest: {guest_name}\n"
		output += f"- Dates: {check_in} to {check_out}\n"
		output += f"- Total Price: {booking['total_price_bdt']} BDT\n"
		return output
	except Exception as e:
		return f"ERROR: Could not create booking: {str(e)}"


@tool
def escalate(reason: str) -> str:
	"""
	Use this tool when the user has a complex request, complaint, or wants to talk to a human.
	It will signal the system to transfer the conversation to a human support agent.
	
	Why it's needed: Bots shouldn't handle arguments or refund disputes! This acts like an "emergency exit"
	button for the LLM to easily hand the interaction over to real customer support.
	"""
	return "I am connecting you to a human agent who can assist with this request. They will be with you shortly!"
