import unittest
import re
from unittest.mock import Mock, AsyncMock, patch
from aiogram.types import Message, Chat
from agents.telegram_listener import (
    SOLANA_CONTRACT_REGEX, 
    TICKER_REGEX,
    is_target_channel,
    inject_into_pipeline,
    handle_channel_post
)
class TestTelegramListener(unittest.TestCase):
    def test_solana_contract_regex(self):
        """Test Solana contract address regex pattern"""
        valid_addresses = [
            "11111111111111111111111111111111111111111",
            "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
            "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        ]
        
        invalid_addresses = [
            "123",
            "012345678901234567890123456789012345678901234567890",
            "0OIOlI",
        ]
        
        for addr in valid_addresses:
            match = SOLANA_CONTRACT_REGEX.search(addr)
            self.assertIsNotNone(match, f"Should match: {addr}")
            self.assertEqual(match.group(0), addr)
        
        for addr in invalid_addresses:
            match = SOLANA_CONTRACT_REGEX.search(addr)
            self.assertIsNone(match, f"Should not match: {addr}")
    
    def test_ticker_regex(self):
        """Test ticker regex pattern"""
        test_cases = [
            ("$SOL", "SOL"),
            ("$PUMP", "PUMP"),
            ("$BTC", "BTC"),
            ("$ETH", "ETH"),
            ("$SOME_TOKEN", "SOME_TOKEN"),
            ("$token123", "token123"),
        ]
        
        for input_text, expected_ticker in test_cases:
            match = TICKER_REGEX.search(input_text)
            self.assertIsNotNone(match, f"Should match: {input_text}")
            self.assertEqual(match.group(1), expected_ticker)
    
    def test_ticker_regex_multiple_tickers(self):
        """Test that ticker regex can find multiple tickers in text"""
        text = "Check $SOL and $PUMP for opportunities"
        matches = TICKER_REGEX.findall(text)
        self.assertEqual(len(matches), 2)
        self.assertIn("SOL", matches)
        self.assertIn("PUMP", matches)
    
    def test_contract_and_ticker_extraction(self):
        """Test extracting both contracts and tickers from text"""
        text = "Check $SOL contract 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM or $PUMP 11111111111111111111111111111111111111111"
        
        contracts = SOLANA_CONTRACT_REGEX.findall(text)
        tickers = TICKER_REGEX.findall(text)
        
        self.assertEqual(len(contracts), 2)
        self.assertEqual(len(tickers), 2)
        self.assertIn("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", contracts)
        self.assertIn("11111111111111111111111111111111111111111", contracts)
        self.assertIn("SOL", tickers)
        self.assertIn("PUMP", tickers)
    
    def test_ticker_str_logic(self):
        """Test the ticker_str logic for edge cases"""
        text1 = "Check $SOL contract 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM and 11111111111111111111111111111111111111111"
        contracts1 = SOLANA_CONTRACT_REGEX.findall(text1)
        tickers1 = TICKER_REGEX.findall(text1)
        
        self.assertEqual(len(contracts1), 2)
        self.assertEqual(len(tickers1), 1)
        
        expected_ticker_str = f"${tickers1[0]}" if tickers1 else "N/A"
        self.assertEqual(expected_ticker_str, "$SOL")
    
    def test_ticker_str_logic_no_ticker(self):
        """Test ticker_str logic when no ticker is found"""
        text = "Check contract 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
        contracts = SOLANA_CONTRACT_REGEX.findall(text)
        tickers = TICKER_REGEX.findall(text)
        
        self.assertEqual(len(contracts), 1)
        self.assertEqual(len(tickers), 0)
        
        expected_ticker_str = f"${tickers[0]}" if tickers else "N/A"
        self.assertEqual(expected_ticker_str, "N/A")
    
    def test_is_target_channel(self):
        """Test is_target_channel function"""
        from config import TELEGRAM_CHANNEL_ID
        
        message1 = Mock(spec=Message)
        message1.chat = Mock(spec=Chat)
        message1.chat.id = TELEGRAM_CHANNEL_ID
        
        self.assertTrue(is_target_channel(message1))
        
        message2 = Mock(spec=Message)
        message2.chat = Mock(spec=Chat)
        message2.chat.id = str(TELEGRAM_CHANNEL_ID)
        
        self.assertTrue(is_target_channel(message2))
        
        message3 = Mock(spec=Message)
        message3.chat = Mock(spec=Chat)
        message3.chat.id = 12345
        
        self.assertFalse(is_target_channel(message3))
    
    @patch('agents.telegram_listener.console')
    async def test_inject_into_pipeline(self, mock_console):
        """Test inject_into_pipeline function"""
        result = await inject_into_pipeline("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", "SOL")
        
        self.assertTrue(result)
        mock_console.print.assert_called_once()
        
        call_args = mock_console.print.call_args[0][0]
        self.assertIn("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", call_args)
        self.assertIn("SOL", call_args)
    
    @patch('agents.telegram_listener.console')
    @patch('agents.telegram_listener.is_gpu_ready', new_callable=AsyncMock)
    @patch('agents.telegram_listener.wake_gpu_server')
    async def test_handle_channel_post_with_contract_and_ticker(self, mock_wake, mock_gpu_ready, mock_console):
        """Test handle_channel_post with both contract and ticker"""
        mock_gpu_ready.return_value = True
        
        message = Mock(spec=Message)
        message.text = "Check $SOL contract 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
        message.caption = None
        message.chat = Mock(spec=Chat)
        message.chat.id = 123456789
        
        await handle_channel_post(message)
        
        self.assertTrue(mock_console.print.called)
    
    @patch('agents.telegram_listener.console')
    @patch('agents.telegram_listener.is_gpu_ready', new_callable=AsyncMock)
    @patch('agents.telegram_listener.wake_gpu_server')
    async def test_handle_channel_post_with_contract_no_ticker(self, mock_wake, mock_gpu_ready, mock_console):
        """Test handle_channel_post with contract but no ticker"""
        mock_gpu_ready.return_value = True
        
        message = Mock(spec=Message)
        message.text = "Check contract 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
        message.caption = None
        message.chat = Mock(spec=Chat)
        message.chat.id = 123456789
        
        await handle_channel_post(message)
        
        self.assertTrue(mock_console.print.called)
    
    def test_message_without_text_or_caption(self):
        """Test handle_channel_post with message without text or caption"""
        message = Mock(spec=Message)
        message.text = None
        message.caption = None
        message.chat = Mock(spec=Chat)
        message.chat.id = 123456789
        
        import asyncio
        result = asyncio.run(handle_channel_post(message))
        self.assertIsNone(result)
    
    @patch('agents.telegram_listener.console')
    @patch('agents.telegram_listener.is_gpu_ready', new_callable=AsyncMock)
    @patch('agents.telegram_listener.wake_gpu_server')
    async def test_handle_channel_post_non_target_channel(self, mock_wake, mock_gpu_ready, mock_console):
        """Test handle_channel_post with non-target channel"""
        from config import TELEGRAM_CHANNEL_ID
        
        mock_gpu_ready.return_value = True
        
        message = Mock(spec=Message)
        message.text = "Check $SOL contract 9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
        message.caption = None
        message.chat = Mock(spec=Chat)
        message.chat.id = 999999999
        
        await handle_channel_post(message)
        
        self.assertEqual(mock_console.print.call_count, 0)
if __name__ == '__main__':
    unittest.main()
