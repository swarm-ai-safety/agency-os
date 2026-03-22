"""Unit tests for Agentic Wallet client and x402 protocol."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from agency_os.wallet import AgenticWalletClient, WalletConfig
from agency_os.wallet.models import TransactionStatus, TransactionType, WalletStatus
from agency_os.wallet.x402 import X402Protocol


@pytest.fixture
def wallet_config():
    """Create a test wallet configuration."""
    return WalletConfig(
        cdp_api_key_name="test-key-name",
        cdp_api_key_private_key="test-private-key",
        network="base-sepolia",
        max_transaction_amount_usdc=1000.0,
        max_daily_spend_usdc=5000.0,
    )


@pytest.fixture
def wallet_client(wallet_config):
    """Create a wallet client with mocked CDP."""
    # Mock CDP at import time using sys.modules
    import sys
    from unittest.mock import MagicMock

    mock_cdp = MagicMock()
    mock_cdp.configure = MagicMock()
    sys.modules["cdp"] = mock_cdp

    client = AgenticWalletClient(wallet_config)
    client._cdp_configured = True  # Force configured for testing
    return client


class TestAgenticWalletClient:
    """Tests for AgenticWalletClient."""

    @pytest.mark.asyncio
    async def test_create_wallet(self, wallet_client):
        """Test wallet creation."""
        # Mock CDP wallet creation
        mock_wallet = MagicMock()
        mock_wallet.id = "test-wallet-id"
        mock_wallet.default_address.address_id = "0xTestAddress123"

        with patch("cdp.Wallet.create", return_value=mock_wallet):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )

            assert wallet.id == "test-wallet-id"
            assert wallet.tenant_id == "tenant-123"
            assert wallet.agent_id == "agent-123"
            assert wallet.address == "0xTestAddress123"
            assert wallet.network == "base-sepolia"
            assert wallet.status == WalletStatus.ACTIVE
            assert wallet.balance_usdc == Decimal("0")

    @pytest.mark.asyncio
    async def test_get_wallet(self, wallet_client):
        """Test wallet retrieval."""
        # Create a wallet first
        mock_wallet = MagicMock()
        mock_wallet.id = "test-wallet-id"
        mock_wallet.default_address.address_id = "0xTestAddress123"

        with patch("cdp.Wallet.create", return_value=mock_wallet):
            created = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )
            retrieved = await wallet_client.get_wallet(created.id)

            assert retrieved is not None
            assert retrieved.id == created.id
            assert retrieved.agent_id == "agent-123"

    @pytest.mark.asyncio
    async def test_get_wallet_by_agent(self, wallet_client):
        """Test wallet retrieval by agent ID."""
        mock_wallet = MagicMock()
        mock_wallet.id = "test-wallet-id"
        mock_wallet.default_address.address_id = "0xTestAddress123"

        with patch("cdp.Wallet.create", return_value=mock_wallet):
            await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )
            retrieved = await wallet_client.get_wallet_by_agent("agent-123")

            assert retrieved is not None
            assert retrieved.agent_id == "agent-123"

    @pytest.mark.asyncio
    async def test_get_balance(self, wallet_client):
        """Test balance retrieval."""
        mock_wallet_create = MagicMock()
        mock_wallet_create.id = "test-wallet-id"
        mock_wallet_create.default_address.address_id = "0xTestAddress123"

        mock_wallet_fetch = MagicMock()
        mock_wallet_fetch.balance.return_value = 100.50

        with (
            patch(
                "cdp.Wallet.create",
                return_value=mock_wallet_create,
            ),
            patch(
                "cdp.Wallet.fetch",
                return_value=mock_wallet_fetch,
            ),
        ):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )
            balance = await wallet_client.get_balance(wallet.id)

            assert balance == Decimal("100.50")

    @pytest.mark.asyncio
    async def test_send_transaction_success(self, wallet_client):
        """Test successful transaction sending."""
        # Setup mocks
        mock_wallet_create = MagicMock()
        mock_wallet_create.id = "test-wallet-id"
        mock_wallet_create.default_address.address_id = "0xSenderAddress"

        mock_wallet_fetch = MagicMock()
        mock_wallet_fetch.balance.return_value = 1000.0

        mock_transfer = MagicMock()
        mock_transfer.transfer_id = "transfer-123"
        mock_transfer.status = "complete"
        mock_transfer.transaction.transaction_hash = "0xTxHash123"
        mock_wallet_fetch.transfer.return_value = mock_transfer

        with (
            patch(
                "cdp.Wallet.create",
                return_value=mock_wallet_create,
            ),
            patch(
                "cdp.Wallet.fetch",
                return_value=mock_wallet_fetch,
            ),
        ):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )
            tx = await wallet_client.send_transaction(
                wallet_id=wallet.id,
                to_address="0xRecipientAddress",
                amount_usdc=Decimal("100.00"),
            )

            assert tx.type == TransactionType.SEND
            assert tx.status == TransactionStatus.CONFIRMED
            assert tx.amount_usdc == Decimal("100.00")
            assert tx.to_address == "0xRecipientAddress"
            assert tx.tx_hash == "0xTxHash123"

    @pytest.mark.asyncio
    async def test_send_transaction_exceeds_limit(self, wallet_client):
        """Test transaction amount validation."""
        mock_wallet = MagicMock()
        mock_wallet.id = "test-wallet-id"
        mock_wallet.default_address.address_id = "0xTestAddress"

        with patch("cdp.Wallet.create", return_value=mock_wallet):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )

            with pytest.raises(ValueError, match="exceeds max limit"):
                await wallet_client.send_transaction(
                    wallet_id=wallet.id,
                    to_address="0xRecipient",
                    amount_usdc=Decimal("10000.00"),  # Exceeds 1000 limit
                )

    @pytest.mark.asyncio
    async def test_send_transaction_insufficient_balance(self, wallet_client):
        """Test insufficient balance check."""
        mock_wallet_create = MagicMock()
        mock_wallet_create.id = "test-wallet-id"
        mock_wallet_create.default_address.address_id = "0xSenderAddress"

        mock_wallet_fetch = MagicMock()
        mock_wallet_fetch.balance.return_value = 50.0  # Low balance

        with (
            patch(
                "cdp.Wallet.create",
                return_value=mock_wallet_create,
            ),
            patch(
                "cdp.Wallet.fetch",
                return_value=mock_wallet_fetch,
            ),
        ):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )

            with pytest.raises(ValueError, match="Insufficient balance"):
                await wallet_client.send_transaction(
                    wallet_id=wallet.id,
                    to_address="0xRecipient",
                    amount_usdc=Decimal("100.00"),
                )


class TestX402Protocol:
    """Tests for x402 protocol."""

    def test_create_payment_headers(self):
        """Test payment-required headers creation."""
        protocol = X402Protocol()
        headers = protocol.create_payment_headers(
            amount_usdc=Decimal("10.50"),
            recipient_address="0xRecipient123",
            network="base",
            memo="Test payment",
            payment_id="payment-123",
        )

        assert headers["X-Payment-Required"] == "true"
        assert headers["X-Payment-Amount"] == "10.50"
        assert headers["X-Payment-Address"] == "0xRecipient123"
        assert headers["X-Payment-Network"] == "base"
        assert headers["X-Payment-Memo"] == "Test payment"
        assert headers["X-Payment-Id"] == "payment-123"

    def test_parse_payment_request(self):
        """Test parsing payment request from headers."""
        protocol = X402Protocol()
        headers = {
            "X-Payment-Required": "true",
            "X-Payment-Amount": "25.75",
            "X-Payment-Address": "0xRecipient456",
            "X-Payment-Network": "base",
            "X-Payment-Memo": "API access",
        }

        request = protocol.parse_payment_request(headers)

        assert request.amount_usdc == Decimal("25.75")
        assert request.recipient_address == "0xRecipient456"
        assert request.network == "base"
        assert request.memo == "API access"

    def test_parse_payment_request_missing_required(self):
        """Test parsing fails with missing required headers."""
        protocol = X402Protocol()
        headers = {
            "X-Payment-Required": "true",
            # Missing X-Payment-Amount and X-Payment-Address
        }

        with pytest.raises(ValueError, match="Missing required header"):
            protocol.parse_payment_request(headers)

    def test_parse_payment_proof(self):
        """Test parsing payment proof from headers."""
        protocol = X402Protocol()
        headers = {"X-Payment-Proof": "0xTxHash123:0xSender789:50.00:base:payment-456"}

        proof = protocol.parse_payment_proof(headers)

        assert proof is not None
        assert proof.transaction_hash == "0xTxHash123"
        assert proof.sender_address == "0xSender789"
        assert proof.amount_usdc == Decimal("50.00")
        assert proof.network == "base"
        assert proof.payment_id == "payment-456"

    def test_parse_payment_proof_no_header(self):
        """Test parsing returns None when no proof header."""
        protocol = X402Protocol()
        headers = {}

        proof = protocol.parse_payment_proof(headers)

        assert proof is None

    def test_create_proof_header(self):
        """Test creating proof header value."""
        protocol = X402Protocol()
        header = protocol.create_proof_header(
            transaction_hash="0xABC123",
            sender_address="0xSender",
            amount_usdc=Decimal("100.00"),
            network="base",
            payment_id="pay-789",
        )

        assert header == "0xABC123:0xSender:100.00:base:pay-789"

    @pytest.mark.asyncio
    async def test_verify_payment_success(self):
        """Test successful payment verification."""
        protocol = X402Protocol()

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"verified": True}

        with patch.object(protocol._client, "post", return_value=mock_response):
            from agency_os.wallet.x402 import X402PaymentProof

            proof = X402PaymentProof(
                transaction_hash="0xTxHash",
                sender_address="0xSender",
                amount_usdc=Decimal("50.00"),
                network="base",
            )

            verified = await protocol.verify_payment(
                proof=proof,
                expected_amount=Decimal("50.00"),
                expected_recipient="0xRecipient",
            )

            assert verified is True

    @pytest.mark.asyncio
    async def test_verify_payment_failure(self):
        """Test failed payment verification."""
        protocol = X402Protocol()

        # Mock HTTP client with rejection
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "verified": False,
            "reason": "Amount mismatch",
        }

        with patch.object(protocol._client, "post", return_value=mock_response):
            from agency_os.wallet.x402 import X402PaymentProof

            proof = X402PaymentProof(
                transaction_hash="0xTxHash",
                sender_address="0xSender",
                amount_usdc=Decimal("25.00"),
                network="base",
            )

            verified = await protocol.verify_payment(
                proof=proof,
                expected_amount=Decimal("50.00"),  # Amount mismatch
                expected_recipient="0xRecipient",
            )

            assert verified is False

    @pytest.mark.asyncio
    async def test_daily_spend_tracking(self, wallet_client):
        """Test daily spend limit enforcement."""
        mock_wallet_create = MagicMock()
        mock_wallet_create.id = "test-wallet-id"
        mock_wallet_create.default_address.address_id = "0xSenderAddress"

        mock_wallet_fetch = MagicMock()
        mock_wallet_fetch.balance.return_value = 10000.0  # High balance

        mock_transfer = MagicMock()
        mock_transfer.transfer_id = "transfer-123"
        mock_transfer.status = "complete"
        mock_transfer.transaction.transaction_hash = "0xTxHash123"
        mock_wallet_fetch.transfer.return_value = mock_transfer

        with (
            patch("cdp.Wallet.create", return_value=mock_wallet_create),
            patch("cdp.Wallet.fetch", return_value=mock_wallet_fetch),
        ):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )

            # Send transactions up to daily limit (5000 USDC total)
            # Each transaction is under the per-tx limit (1000)
            for _ in range(5):
                await wallet_client.send_transaction(
                    wallet_id=wallet.id,
                    to_address="0xRecipient",
                    amount_usdc=Decimal("1000.00"),
                )

            # Try to send one more transaction (would exceed daily limit)
            with pytest.raises(ValueError, match="Daily spend limit exceeded"):
                await wallet_client.send_transaction(
                    wallet_id=wallet.id,
                    to_address="0xRecipient",
                    amount_usdc=Decimal("100.00"),
                )

    @pytest.mark.asyncio
    async def test_export_rate_limiting(self, wallet_client):
        """Test wallet export rate limiting."""
        mock_wallet_create = MagicMock()
        mock_wallet_create.id = "test-wallet-id"
        mock_wallet_create.default_address.address_id = "0xTestAddress"

        mock_wallet_fetch = MagicMock()
        mock_export_data = MagicMock()
        mock_export_data.to_dict.return_value = {"wallet_id": "test", "seed": "secret"}
        mock_wallet_fetch.export.return_value = mock_export_data

        with (
            patch("cdp.Wallet.create", return_value=mock_wallet_create),
            patch("cdp.Wallet.fetch", return_value=mock_wallet_fetch),
        ):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )

            # First export should succeed
            export1 = await wallet_client.export_wallet(wallet.id)
            assert export1 is not None

            # Second immediate export should fail (rate limited)
            with pytest.raises(RuntimeError, match="Export rate limit"):
                await wallet_client.export_wallet(wallet.id)

    @pytest.mark.asyncio
    async def test_export_log_is_redacted(self, wallet_client):
        """Test wallet export logs do not include sensitive-material hints."""
        mock_wallet_create = MagicMock()
        mock_wallet_create.id = "test-wallet-id"
        mock_wallet_create.default_address.address_id = "0xTestAddress"

        mock_wallet_fetch = MagicMock()
        mock_export_data = MagicMock()
        mock_export_data.to_dict.return_value = {"wallet_id": "test", "seed": "secret"}
        mock_wallet_fetch.export.return_value = mock_export_data

        with (
            patch("cdp.Wallet.create", return_value=mock_wallet_create),
            patch("cdp.Wallet.fetch", return_value=mock_wallet_fetch),
            patch(
                "agency_os.wallet_private.agentic_client.logger.warning"
            ) as mock_warning,
        ):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )
            await wallet_client.export_wallet(wallet.id)

        mock_warning.assert_called_with(
            "Wallet export completed for wallet_id=%s",
            "test-wallet-id",
        )

    @pytest.mark.asyncio
    async def test_audit_logging(self, wallet_client):
        """Test audit logging for wallet operations."""
        mock_wallet = MagicMock()
        mock_wallet.id = "test-wallet-id"
        mock_wallet.default_address.address_id = "0xTestAddress"

        with patch("cdp.Wallet.create", return_value=mock_wallet):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-123"
            )

            # Check that audit event was logged
            events = wallet_client._audit.get_recent_events()
            assert len(events) == 1
            assert events[0].event_type.value == "wallet_created"
            assert events[0].wallet_id == wallet.id
            assert events[0].agent_id == "agent-123"


class TestX402ReplayPrevention:
    """Tests for x402 payment replay prevention."""

    @pytest.mark.asyncio
    async def test_payment_replay_prevention(self):
        """Test that verified payments are cached to prevent replay."""
        protocol = X402Protocol(cache_ttl_seconds=3600)

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"verified": True}

        from agency_os.wallet.x402 import X402PaymentProof

        proof = X402PaymentProof(
            transaction_hash="0xTxHash",
            sender_address="0xSender",
            amount_usdc=Decimal("50.00"),
            network="base",
        )

        with patch.object(protocol._client, "post", return_value=mock_response):
            # First verification should call API
            verified1 = await protocol.verify_payment(
                proof=proof,
                expected_amount=Decimal("50.00"),
                expected_recipient="0xRecipient",
            )
            assert verified1 is True

        # Second verification with same tx_hash should use cache (no API call)
        verified2 = await protocol.verify_payment(
            proof=proof,
            expected_amount=Decimal("50.00"),
            expected_recipient="0xRecipient",
        )
        assert verified2 is True

    @pytest.mark.asyncio
    async def test_replay_attack_detection(self):
        """Test detection of replay attack with different parameters."""
        protocol = X402Protocol(cache_ttl_seconds=3600)

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"verified": True}

        from agency_os.wallet.x402 import X402PaymentProof

        proof1 = X402PaymentProof(
            transaction_hash="0xTxHash",
            sender_address="0xSender",
            amount_usdc=Decimal("50.00"),
            network="base",
        )

        with patch.object(protocol._client, "post", return_value=mock_response):
            # First verification for 50 USDC to recipient A
            verified1 = await protocol.verify_payment(
                proof=proof1,
                expected_amount=Decimal("50.00"),
                expected_recipient="0xRecipientA",
            )
            assert verified1 is True

        # Attempt to replay same tx for different amount/recipient
        proof2 = X402PaymentProof(
            transaction_hash="0xTxHash",  # Same tx hash!
            sender_address="0xSender",
            amount_usdc=Decimal("100.00"),  # Different amount
            network="base",
        )

        # Should detect replay attack and reject
        verified2 = await protocol.verify_payment(
            proof=proof2,
            expected_amount=Decimal("100.00"),
            expected_recipient="0xRecipientB",  # Different recipient
        )
        assert verified2 is False  # Replay detected


class TestAuditLogger:
    """Tests for audit logging."""

    def test_audit_logger_wallet_created(self):
        """Test wallet creation audit log."""
        from agency_os.wallet.audit import AuditEventType, AuditLogger

        logger = AuditLogger()
        logger.wallet_created(
            wallet_id="wallet-123",
            agent_id="agent-456",
            address="0xAddress",
            network="base-sepolia",
        )

        events = logger.get_recent_events()
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.WALLET_CREATED
        assert events[0].wallet_id == "wallet-123"
        assert events[0].agent_id == "agent-456"

    def test_audit_logger_transaction_sent(self):
        """Test transaction audit log."""
        from agency_os.wallet.audit import AuditEventType, AuditLogger

        logger = AuditLogger()
        logger.transaction_sent(
            transaction_id="tx-123",
            wallet_id="wallet-456",
            agent_id="agent-789",
            amount_usdc=Decimal("100.50"),
            to_address="0xRecipient",
            from_address="0xSender",
            network="base",
            status="confirmed",
        )

        events = logger.get_recent_events()
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.TRANSACTION_SENT
        assert events[0].transaction_id == "tx-123"
        assert events[0].amount_usdc == Decimal("100.50")

    def test_audit_logger_payment_verified(self):
        """Test payment verification audit log."""
        from agency_os.wallet.audit import AuditEventType, AuditLogger

        logger = AuditLogger()
        logger.payment_verified(
            transaction_hash="0xTxHash",
            sender_address="0xSender",
            amount_usdc=Decimal("50.00"),
            recipient_address="0xRecipient",
            network="base",
        )

        events = logger.get_recent_events()
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.PAYMENT_VERIFIED
        assert events[0].status == "verified"


class TestWalletTenantIsolation:
    """Security tests for wallet tenant isolation."""

    @pytest.mark.asyncio
    async def test_wallet_has_tenant_id(self, wallet_client):
        """Test that wallets are created with tenant_id."""
        mock_wallet = MagicMock()
        mock_wallet.id = "test-wallet-id"
        mock_wallet.default_address.address_id = "0xTestAddress"

        with patch("cdp.Wallet.create", return_value=mock_wallet):
            wallet = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-abc"
            )

            assert wallet.tenant_id == "tenant-abc"
            assert wallet.agent_id == "agent-123"

    @pytest.mark.asyncio
    async def test_different_tenants_create_separate_wallets(self, wallet_client):
        """Test that different tenants create separate wallet instances."""
        mock_wallet1 = MagicMock()
        mock_wallet1.id = "wallet-1"
        mock_wallet1.default_address.address_id = "0xAddress1"

        mock_wallet2 = MagicMock()
        mock_wallet2.id = "wallet-2"
        mock_wallet2.default_address.address_id = "0xAddress2"

        with patch("cdp.Wallet.create", side_effect=[mock_wallet1, mock_wallet2]):
            wallet1 = await wallet_client.create_wallet(
                agent_id="agent-123", tenant_id="tenant-A"
            )
            wallet2 = await wallet_client.create_wallet(
                agent_id="agent-456", tenant_id="tenant-B"
            )

            assert wallet1.tenant_id == "tenant-A"
            assert wallet2.tenant_id == "tenant-B"
            assert wallet1.id != wallet2.id

    @pytest.mark.asyncio
    async def test_import_wallet_preserves_tenant_id(self, wallet_client):
        """Test that imported wallets have tenant_id set correctly."""
        # Mock CDP modules
        import sys

        mock_cdp_wallet_data = MagicMock()
        mock_wallet_data = MagicMock()
        mock_cdp_wallet_data.WalletData.from_dict.return_value = mock_wallet_data
        sys.modules["cdp.wallet_data"] = mock_cdp_wallet_data

        mock_imported_wallet = MagicMock()
        mock_imported_wallet.id = "imported-wallet-id"
        mock_imported_wallet.default_address.address_id = "0xImportedAddress"
        mock_imported_wallet.network_id = "base-sepolia"

        with patch("cdp.Wallet.import_data", return_value=mock_imported_wallet):
            wallet = await wallet_client.import_wallet(
                export_data={"seed": "test-seed"},
                agent_id="agent-789",
                tenant_id="tenant-XYZ",
            )

            assert wallet.tenant_id == "tenant-XYZ"
            assert wallet.agent_id == "agent-789"
