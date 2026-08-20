import os
import time
import base64
import requests

from solders.transaction import VersionedTransaction


SOLANA_RPC_URL = os.getenv(
    "SOLANA_RPC_URL",
    "https://api.mainnet-beta.solana.com",
)


class SolanaSenderError(Exception):
    pass


class SolanaSender:

    def __init__(
        self,
        rpc_url=None,
        timeout=15,
        confirm_timeout=30,
        poll_interval=1.0,
    ):
        self.rpc_url = rpc_url or SOLANA_RPC_URL
        self.timeout = float(timeout)
        self.confirm_timeout = float(confirm_timeout)
        self.poll_interval = float(poll_interval)

    def _rpc(self, method, params):

        try:
            response = requests.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()
            data = response.json()

        except requests.RequestException as exc:
            raise SolanaSenderError(
                f"RPC request failed: {exc}"
            ) from exc

        except ValueError as exc:
            raise SolanaSenderError(
                "RPC returned invalid JSON"
            ) from exc

        if "error" in data:
            raise SolanaSenderError(
                f"RPC {method} error: {data['error']}"
            )

        if "result" not in data:
            raise SolanaSenderError(
                f"RPC {method} returned no result"
            )

        return data["result"]

    def send(self, transaction):

        # Defense-in-depth: never submit a real Solana
        # transaction unless LIVE_TRADING is explicitly enabled.
        live_enabled = os.getenv(
            "LIVE_TRADING",
            "False",
        ).lower() in (
            "true",
            "1",
            "yes",
        )

        if not live_enabled:
            raise SolanaSenderError(
                "Transaction submission blocked: "
                "LIVE_TRADING is disabled"
            )

        if not isinstance(
            transaction,
            VersionedTransaction,
        ):
            raise SolanaSenderError(
                "Expected VersionedTransaction"
            )

        raw = bytes(transaction)

        encoded = base64.b64encode(
            raw
        ).decode("ascii")

        signature = self._rpc(
            "sendTransaction",
            [
                encoded,
                {
                    "encoding": "base64",
                    "skipPreflight": False,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 3,
                },
            ],
        )

        if not signature:
            raise SolanaSenderError(
                "Solana returned no transaction signature"
            )

        return str(signature)

    def confirm(self, signature):

        started = time.time()

        while (
            time.time() - started
            < self.confirm_timeout
        ):

            result = self._rpc(
                "getSignatureStatuses",
                [
                    [signature],
                    {
                        "searchTransactionHistory": True,
                    },
                ],
            )

            values = result.get("value", [])

            status = (
                values[0]
                if values
                else None
            )

            if status is not None:

                error = status.get("err")

                if error is not None:
                    raise SolanaSenderError(
                        f"Transaction failed: {error}"
                    )

                confirmation = status.get(
                    "confirmationStatus"
                )

                if confirmation in (
                    "confirmed",
                    "finalized",
                ):
                    return {
                        "signature": signature,
                        "confirmation_status": confirmation,
                        "slot": status.get("slot"),
                    }

            time.sleep(
                self.poll_interval
            )

        raise SolanaSenderError(
            "Transaction confirmation timed out"
        )

    def send_and_confirm(self, transaction):

        signature = self.send(transaction)

        return self.confirm(signature)
