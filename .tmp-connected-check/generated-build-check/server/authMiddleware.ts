import type { Request, Response, NextFunction } from "express";

const AUTH_API_URL = "https://xvaz-5ufg-teim.n7e.xano.io/api:rVbvzJH3";
const DATA_API_URL = "https://xvaz-5ufg-teim.n7e.xano.io/api:SuvYKY7H";

interface User {
  id: string;
  email: string;
  name: string;
  username: string;
}

interface AccountStatus {
  id: string;
  user_id: string;
  plan_tier: string;
}

// Extend Express Request to include user
declare global {
  namespace Express {
    interface Request {
      user?: User;
      accountStatus?: AccountStatus;
    }
  }
}

/**
 * Middleware to verify JWT token and authenticate user
 */
export async function requireAuth(req: Request, res: Response, next: NextFunction) {
  try {
    const authHeader = req.headers.authorization;
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      console.error('❌ Auth error: No authorization header or invalid format');
      return res.status(401).json({ error: 'Authentication required' });
    }

    const token = authHeader.substring(7); // Remove 'Bearer ' prefix

    // Verify token with Xano
    const response = await fetch(`${AUTH_API_URL}/auth/me`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`❌ Token validation failed: ${response.status} - ${errorText}`);
      return res.status(401).json({ error: 'Invalid or expired token' });
    }

    const user = await response.json();
    req.user = user;
    
    next();
  } catch (error) {
    console.error('Auth middleware error:', error);
    return res.status(401).json({ error: 'Authentication failed' });
  }
}

/**
 * Middleware to verify user has admin plan tier
 */
export async function requireAdmin(req: Request, res: Response, next: NextFunction) {
  try {
    if (!req.user) {
      return res.status(401).json({ error: 'Authentication required' });
    }

    const authHeader = req.headers.authorization;
    const token = authHeader?.substring(7);

    // Fetch account status
    const response = await fetch(`${DATA_API_URL}/account_status?user_id=${req.user.id}`, {
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      return res.status(403).json({ error: 'Access denied' });
    }

    const accountStatuses = await response.json();
    const accountStatus = Array.isArray(accountStatuses) 
      ? accountStatuses.find((s: AccountStatus) => s.user_id === req.user?.id)
      : accountStatuses;

    if (!accountStatus || accountStatus.plan_tier !== 'admin') {
      return res.status(403).json({ error: 'Admin access required' });
    }

    req.accountStatus = accountStatus;
    next();
  } catch (error) {
    console.error('Admin middleware error:', error);
    return res.status(403).json({ error: 'Access denied' });
  }
}
