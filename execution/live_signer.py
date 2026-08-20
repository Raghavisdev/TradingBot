import json
import os
from pathlib import Path

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction


class LiveSignerError(Exception):
    pass


class LiveSigner:

    """
    Controlled signer for Solana transactions.

    HARD SAFETY RULE:

        LIVE_TRADING must explicitly be enabled before
        any private key is loaded or any transaction is signed.

    The private key is loaded only from LIVE_KEYPAIR_PATH.
    The private key is never printed or logged.
    """

    def __init__(
        self,
        expected_public_key,
        key_path=None,
    ):

        self.expected_public_key = str(
            expected_public_key
        )

        configured_path = (
            key_path
            if key_path is not None
            else os.getenv(
                "LIVE_KEYPAIR_PATH",
                "",
            )
        )

        if not configured_path:

            raise LiveSignerError(
                "LIVE_KEYPAIR_PATH is not configured"
            )

        self.key_path = Path(
            configured_path
        )

        self.live_enabled = (
            os.getenv(
                "LIVE_TRADING",
                "False",
            ).lower()
            in (
                "true",
                "1",
                "yes",
            )
        )

    # ======================================================
    # LOAD KEYPAIR
    # ======================================================

    def _load_keypair(self):

        if not self.live_enabled:

            raise LiveSignerError(
                "Signing blocked: LIVE_TRADING is disabled"
            )

        if not self.key_path.exists():

            raise LiveSignerError(
                f"Keypair file does not exist: "
                f"{self.key_path}"
            )

        if not self.key_path.is_file():

            raise LiveSignerError(
                "Keypair path is not a regular file"
            )

        try:

            raw = self.key_path.read_text(
                encoding="utf-8"
            ).strip()

        except OSError as exc:

            raise LiveSignerError(
                f"Unable to read keypair file: {exc}"
            ) from exc

        if not raw:

            raise LiveSignerError(
                "Keypair file is empty"
            )

        try:

            secret = json.loads(raw)

        except Exception as exc:

            raise LiveSignerError(
                "Keypair file is not valid JSON"
            ) from exc

        if not isinstance(
            secret,
            list,
        ):

            raise LiveSignerError(
                "Keypair JSON must contain an array"
            )

        if len(secret) != 64:

            raise LiveSignerError(
                "Keypair must contain exactly 64 bytes"
            )

        try:

            values = []

            for value in secret:

                value = int(value)

                if not 0 <= value <= 255:

                    raise ValueError(
                        "byte outside range"
                    )

                values.append(value)

            secret_bytes = bytes(
                values
            )

        except Exception as exc:

            raise LiveSignerError(
                "Keypair contains invalid byte values"
            ) from exc

        try:

            keypair = Keypair.from_bytes(
                secret_bytes
            )

        except Exception as exc:

            raise LiveSignerError(
                "Failed to construct Solana keypair"
            ) from exc

        # ==================================================
        # WALLET MATCH
        # ==================================================

        derived_public_key = str(
            keypair.pubkey()
        )

        if (
            derived_public_key
            != self.expected_public_key
        ):

            raise LiveSignerError(
                "Keypair public key does not match "
                "configured wallet"
            )

        return keypair

    # ======================================================
    # SIGN
    # ======================================================

    def sign(
        self,
        transaction: VersionedTransaction,
    ):

        if not isinstance(
            transaction,
            VersionedTransaction,
        ):

            raise LiveSignerError(
                "Expected VersionedTransaction"
            )

        keypair = self._load_keypair()

        try:

            signed = VersionedTransaction(
                transaction.message,
                [keypair],
            )

        except Exception as exc:

            raise LiveSignerError(
                f"Transaction signing failed: {exc}"
            ) from exc

        return signed

    # ======================================================
    # VERIFY SIGNATURE
    # ======================================================

    def verify_signed_transaction(
        self,
        transaction: VersionedTransaction,
    ):

        if not isinstance(
            transaction,
            VersionedTransaction,
        ):

            raise LiveSignerError(
                "Expected VersionedTransaction"
            )

        try:

            signatures = transaction.signatures

        except Exception as exc:

            raise LiveSignerError(
                f"Unable to inspect signatures: {exc}"
            ) from exc

        if not signatures:

            raise LiveSignerError(
                "Signed transaction contains no signatures"
            )

        # The payer must correspond to the expected wallet.
        payer = str(
            transaction.message.account_keys[0]
        )

        if payer != self.expected_public_key:

            raise LiveSignerError(
                "Transaction payer does not match "
                "configured wallet"
            )

        return True
