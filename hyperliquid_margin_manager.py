import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Tuple


class HyperliquidMarginManager:
    """
    A class to manage Hyperliquid margin tiers and calculate appropriate leverage
    for trading positions based on notional value and asset type.
    """
    
    def __init__(self, csv_file_path: str = 'hyperliquid_margin_tiers.csv'):
        """
        Initialize the margin manager with margin tier data.
        
        Args:
            csv_file_path (str): Path to the CSV file containing margin tier data
        """
        self.csv_file_path = csv_file_path
        self.margin_tiers = None
        self.load_margin_tiers()
    
    def load_margin_tiers(self) -> None:
        """Load margin tier data from CSV file."""
        try:
            self.margin_tiers = pd.read_csv(self.csv_file_path)
            print(f"Loaded margin tiers for {len(self.margin_tiers['asset'].unique())} unique assets")
        except FileNotFoundError:
            raise FileNotFoundError(f"Margin tiers CSV file not found: {self.csv_file_path}")
        except Exception as e:
            raise Exception(f"Error loading margin tiers: {str(e)}")
    
    def get_max_leverage(self, asset: str, notional_value: float, network: str = 'mainnet') -> Optional[int]:
        """
        Get the maximum leverage for a given asset and notional position value.
        
        Args:
            asset (str): Asset symbol (e.g., 'BTC', 'ETH')
            notional_value (float): Notional position value in USD
            network (str): Network type ('mainnet' or 'testnet')
        
        Returns:
            Optional[int]: Maximum leverage allowed, or None if asset not found
        """
        # Filter data for the specific asset and network
        asset_data = self.margin_tiers[
            (self.margin_tiers['asset'] == asset.upper()) & 
            (self.margin_tiers['network'] == network.lower())
        ].copy()
        
        if asset_data.empty:
            return None
        
        # Sort by tier to ensure proper order
        asset_data = asset_data.sort_values('tier')
        
        # Find the appropriate tier based on notional value
        for _, row in asset_data.iterrows():
            if row['min_notional'] <= notional_value <= row['max_notional']:
                return int(row['max_leverage'])
        
        return None
    
    def get_maintenance_margin_rate(self, max_leverage: int) -> float:
        """
        Calculate maintenance margin rate based on maximum leverage.
        Formula: maintenance_margin_rate = (Initial Margin Rate at Maximum leverage) / 2
        Initial Margin Rate = 1 / max_leverage
        
        Args:
            max_leverage (int): Maximum leverage for the tier
        
        Returns:
            float: Maintenance margin rate as a decimal (e.g., 0.025 for 2.5%)
        """
        if max_leverage <= 0:
            raise ValueError("Max leverage must be positive")
        
        initial_margin_rate = 1.0 / max_leverage
        maintenance_margin_rate = initial_margin_rate / 2.0
        return maintenance_margin_rate
    
    def calculate_maintenance_margin(self, asset: str, notional_value: float, 
                                   network: str = 'mainnet') -> Optional[Dict]:
        """
        Calculate maintenance margin for a position.
        
        Args:
            asset (str): Asset symbol
            notional_value (float): Notional position value in USD
            network (str): Network type
        
        Returns:
            Optional[Dict]: Dictionary with margin calculation details or None if asset not found
        """
        max_leverage = self.get_max_leverage(asset, notional_value, network)
        if max_leverage is None:
            return None
        
        maintenance_margin_rate = self.get_maintenance_margin_rate(max_leverage)
        
        # For simplified calculation, we'll use the basic formula
        # maintenance_margin = notional_position_value * maintenance_margin_rate - maintenance_deduction
        # Note: Full maintenance_deduction calculation would require iterating through all tiers
        maintenance_margin = notional_value * maintenance_margin_rate
        
        return {
            'asset': asset,
            'notional_value': notional_value,
            'max_leverage': max_leverage,
            'maintenance_margin_rate': maintenance_margin_rate,
            'maintenance_margin_rate_percent': maintenance_margin_rate * 100,
            'maintenance_margin': maintenance_margin,
            'network': network
        }
    
    def get_optimal_leverage(self, asset: str, notional_value: float, 
                           risk_factor: float = 0.8, network: str = 'mainnet') -> Optional[float]:
        """
        Get optimal leverage considering a risk factor to stay below maximum.
        
        Args:
            asset (str): Asset symbol
            notional_value (float): Notional position value in USD
            risk_factor (float): Risk reduction factor (0.8 = use 80% of max leverage)
            network (str): Network type
        
        Returns:
            Optional[float]: Optimal leverage considering risk factor
        """
        max_leverage = self.get_max_leverage(asset, notional_value, network)
        if max_leverage is None:
            return None
        
        return max_leverage * risk_factor
    
    def get_supported_assets(self, network: str = 'mainnet') -> List[str]:
        """
        Get list of supported assets for a given network.
        
        Args:
            network (str): Network type ('mainnet' or 'testnet')
        
        Returns:
            List[str]: List of supported asset symbols
        """
        if self.margin_tiers is None:
            return []
        
        assets = self.margin_tiers[
            self.margin_tiers['network'] == network.lower()
        ]['asset'].unique().tolist()
        
        return sorted(assets)
    
    def get_asset_tiers(self, asset: str, network: str = 'mainnet') -> Optional[pd.DataFrame]:
        """
        Get all tiers for a specific asset.
        
        Args:
            asset (str): Asset symbol (normalized, e.g., 'PEPE' not 'kPEPE')
            network (str): Network type
        
        Returns:
            Optional[pd.DataFrame]: DataFrame with all tiers for the asset
        """
        if self.margin_tiers is None:
            return None
        
        asset_tiers = self.margin_tiers[
            (self.margin_tiers['normalized_asset'] == asset.upper()) & 
            (self.margin_tiers['network'] == network.lower())
        ].copy()
        
        if asset_tiers.empty:
            return None
        
        return asset_tiers.sort_values('tier')
    
    def validate_position(self, asset: str, position_size_usd: float, 
                         desired_leverage: float, network: str = 'mainnet') -> Dict:
        """
        Validate if a position with desired leverage is allowed.
        
        Args:
            asset (str): Asset symbol
            position_size_usd (float): Position size in USD
            desired_leverage (float): Desired leverage
            network (str): Network type
        
        Returns:
            Dict: Validation result with status and details
        """
        max_leverage = self.get_max_leverage(asset, position_size_usd, network)
        
        if max_leverage is None:
            return {
                'valid': False,
                'reason': f'Asset {asset} not supported on {network}',
                'max_leverage': None,
                'desired_leverage': desired_leverage
            }
        
        if desired_leverage <= max_leverage:
            return {
                'valid': True,
                'reason': 'Position is valid',
                'max_leverage': max_leverage,
                'desired_leverage': desired_leverage,
                'safety_margin': max_leverage - desired_leverage
            }
        else:
            return {
                'valid': False,
                'reason': f'Desired leverage {desired_leverage}x exceeds maximum {max_leverage}x',
                'max_leverage': max_leverage,
                'desired_leverage': desired_leverage,
                'excess_leverage': desired_leverage - max_leverage
            }


# Example usage and testing functions
def example_usage():
    """Example usage of the HyperliquidMarginManager."""
    
    # Initialize the margin manager
    manager = HyperliquidMarginManager('hyperliquid_margin_tiers.csv')
    
    # Example 1: Get max leverage for BTC with different position sizes
    print("=== BTC Leverage Examples ===")
    btc_positions = [1000000, 50000000, 100000000, 200000000]  # Various USD amounts
    
    for position in btc_positions:
        max_lev = manager.get_max_leverage('BTC', position)
        optimal_lev = manager.get_optimal_leverage('BTC', position, risk_factor=0.8)
        print(f"BTC ${position:,}: Max Leverage: {max_lev}x, Optimal (80%): {optimal_lev:.1f}x")
    
    # Example 2: Get maintenance margin calculation
    print("\n=== Maintenance Margin Calculation ===")
    margin_info = manager.calculate_maintenance_margin('ETH', 50000000)
    if margin_info:
        print(f"Asset: {margin_info['asset']}")
        print(f"Position Size: ${margin_info['notional_value']:,}")
        print(f"Max Leverage: {margin_info['max_leverage']}x")
        print(f"Maintenance Margin Rate: {margin_info['maintenance_margin_rate_percent']:.2f}%")
        print(f"Maintenance Margin: ${margin_info['maintenance_margin']:,.2f}")
    
    # Example 3: Validate positions
    print("\n=== Position Validation ===")
    validations = [
        ('BTC', 10000000, 35),   # Should be valid
        ('BTC', 200000000, 30),  # Should be invalid (exceeds 20x limit)
        ('ETH', 50000000, 20),   # Should be valid
        ('UNKNOWN', 1000000, 10) # Should be invalid (unknown asset)
    ]
    
    for asset, size, leverage in validations:
        result = manager.validate_position(asset, size, leverage)
        status = "✅ VALID" if result['valid'] else "❌ INVALID"
        print(f"{status}: {asset} ${size:,} at {leverage}x - {result['reason']}")
    
    # Example 4: List supported assets
    print(f"\n=== Supported Assets ===")
    mainnet_assets = manager.get_supported_assets('mainnet')
    print(f"Mainnet assets ({len(mainnet_assets)}): {', '.join(mainnet_assets[:10])}...")


if __name__ == "__main__":
    example_usage()