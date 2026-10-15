"""Application exceptions and their HTTP error-handler registration.

Services raise these instead of signalling failures through ``ValueError``
message strings; a single Flask error handler maps them to JSON responses.
"""

from http import HTTPStatus

from flask import Flask, jsonify
from flask.typing import ResponseReturnValue
from pydantic import ValidationError


class AppError(Exception):
    """Base class for errors that map directly to an HTTP response."""

    status_code: HTTPStatus = HTTPStatus.INTERNAL_SERVER_ERROR

    def __init__(self, message: str) -> None:
        """Create the error.

        Args:
            message: Human-readable message returned to the client.
        """
        super().__init__(message)
        self.message = message


class BadRequestError(AppError):
    """The request was malformed (missing or unparseable parameters)."""

    status_code = HTTPStatus.BAD_REQUEST


class NotFoundError(AppError):
    """A requested resource does not exist."""

    status_code = HTTPStatus.NOT_FOUND


class ConflictError(AppError):
    """The request conflicts with existing data (e.g. referenced rows)."""

    status_code = HTTPStatus.CONFLICT


class UnprocessableError(AppError):
    """The request was well-formed but its content can't be processed."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


class InsufficientDataError(UnprocessableError):
    """Too few usable data points to fit a model."""


class CoffeeNotFoundError(NotFoundError):
    """No coffee with the requested id."""

    def __init__(self) -> None:
        """Create the error with the API's standard message."""
        super().__init__("coffee not found")


class NoRoastDateError(NotFoundError):
    """The coffee has no roast date, so bean age can't be computed."""

    def __init__(self) -> None:
        """Create the error with the API's standard message."""
        super().__init__("coffee has no roast_date")


class GrinderNotFoundError(NotFoundError):
    """No grinder with the requested id."""

    def __init__(self) -> None:
        """Create the error with the API's standard message."""
        super().__init__("grinder not found")


class NoTrainingError(NotFoundError):
    """No grind model training exists for the grinder (and filters)."""

    def __init__(self) -> None:
        """Create the error with the API's standard message."""
        super().__init__("no trained model found for this grinder")


def register_error_handlers(app: Flask) -> None:
    """Attach JSON error handlers for AppError and Pydantic validation errors.

    Args:
        app: Flask application.
    """

    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError) -> ResponseReturnValue:
        """Return the error's message with its HTTP status."""
        return jsonify({"error": exc.message}), exc.status_code

    @app.errorhandler(ValidationError)
    def handle_validation_error(exc: ValidationError) -> ResponseReturnValue:
        """Return 422 for Pydantic validation failures."""
        return {"errors": exc.errors()}, HTTPStatus.UNPROCESSABLE_ENTITY
