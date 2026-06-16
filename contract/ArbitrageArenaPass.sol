// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract ArbitrageArenaPass {
    address public immutable owner;
    IERC20 public immutable paymentToken; // e.g., USDT or USDC ERC20 address

    uint256 public weeklyPrice = 10 * 10**6;  // $10.00 (Assuming 6 decimals for USDT/USDC)
    uint256 public monthlyPrice = 30 * 10**6; // $30.00

    struct Subscription {
        uint256 expiresAt;
        bool isActive;
    }

    mapping(address => Subscription) public memberships;

    event SubscriptionPurchased(address indexed user, uint256 expirationTime, uint256 amountPaid);

    modifier onlyOwner() {
        require(msg.sender == owner, "Unauthorized");
        _;
    }

    constructor(address _tokenAddress) {
        owner = msg.sender;
        paymentToken = IERC20(_tokenAddress);
    }

    function purchasePass(bool isMonthly) external {
        uint256 cost = isMonthly ? monthlyPrice : weeklyPrice;
        uint256 duration = isMonthly ? 30 days : 7 days;

        // Secure stablecoin distribution
        require(paymentToken.transferFrom(msg.sender, owner, cost), "Payment execution failed");

        uint256 currentExpiry = memberships[msg.sender].expiresAt;
        uint256 newExpiry = (currentExpiry > block.timestamp) ? currentExpiry + duration : block.timestamp + duration;

        memberships[msg.sender] = Subscription({
            expiresAt: newExpiry,
            isActive: true
        });

        emit SubscriptionPurchased(msg.sender, newExpiry, cost);
    }

    function isMemberValid(address _user) external view returns (bool) {
        return (memberships[_user].isActive && memberships[_user].expiresAt > block.timestamp);
    }

    // Admin calibration panel
    function adjustPricing(uint256 _weekly, uint256 _monthly) external onlyOwner {
        weeklyPrice = _weekly;
        monthlyPrice = _monthly;
    }
}
