#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""认证API路由"""

from fastapi import APIRouter, Depends, HTTPException, status
from src.common.logging import get_logger

logger = get_logger(__name__)

from src.agents.models.requests import LoginRequest, RegisterRequest
from src.agents.models.responses import BaseResponse, LoginResponse, UserInfo
from src.agents.services.auth_service import AuthService
from src.agents.utils.dependencies import get_db_manager, get_current_user

router = APIRouter()
auth_service = AuthService()

@router.post("/login", response_model=BaseResponse[LoginResponse])
async def login(
    request: LoginRequest,
    db = Depends(get_db_manager)
):
    """用户登录"""
    try:
        login_result = await auth_service.login(
            db, request.login_name, request.password
        )
        
        if not login_result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="登录名或密码错误"
            )
        
        return BaseResponse(
            data=LoginResponse(
                token=login_result["token"],
                expire=login_result["expire"],
                user_id=login_result["user_id"]
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"登录失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录失败"
        )

@router.post("/register", response_model=BaseResponse[None])
async def register(
    request: RegisterRequest,
    db = Depends(get_db_manager)
):
    """用户注册"""
    try:
        success = await auth_service.register(
            db, request.user_name, request.login_name, 
            request.password, request.mobile, request.login_type
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="注册失败，用户名或登录名可能已存在"
            )
        
        return BaseResponse(message="注册成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"注册失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="注册失败"
        )

@router.get("/me", response_model=BaseResponse[UserInfo])
async def get_current_user_info(
    user = Depends(get_current_user)
):
    """获取当前用户信息"""
    return BaseResponse(
        data=UserInfo(
            id=user['id'],
            user_name=user['user_name'],
            login_name=user['login_name'],
            mobile=user.get('mobile'),
            avatar=user.get('avatar')
        )
    )

