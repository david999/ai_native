package com.aulton.datacalc.service.impl;

import com.aulton.datacalc.mapper.ChangeBatteryListMapper;
import com.aulton.datacalc.model.dto.IdealEnergyDTO;
import com.aulton.datacalc.model.entity.ChangeBatteryListDO;
import com.aulton.datacalc.service.IdealEnergyService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.Objects;

/**
 * 业务逻辑层 - 理论充电量计算
 *
 * @author 刘梓聪
 * @email liuzicong@aulton.com
 * @date 2026/6/17
 * @Copyright Copyright(c) aulton Inc.AllRightsReserved.
 **/
@Slf4j
@Service
public class IdealEnergyServiceImpl implements IdealEnergyService {

    @Autowired
    private ChangeBatteryListMapper changeBatteryListMapper;

    @Override
    public IdealEnergyDTO getIdealEnergy(String swapNo) {
        // 查询1：根据 swapNo 查询当前换电记录
        ChangeBatteryListDO currentSwap = changeBatteryListMapper.getCurrentSwapBySwapNo(swapNo);
        if (currentSwap == null) {
            log.info("理论充电量计算: swapNo={} 未找到换电记录", swapNo);
            return null;
        }

        // 查询2：根据车牌号查询同一辆车的上一次换电记录
        ChangeBatteryListDO previousSwap = changeBatteryListMapper.getPreviousSwapByPlateNumber(
                currentSwap.getPlateNumber(), currentSwap.getExchangeEndTime());
        if (previousSwap == null) {
            log.info("理论充电量计算: swapNo={} 未找到上次换电记录, plateNumber={}",
                    swapNo, currentSwap.getPlateNumber());
            return null;
        }

        // 约束校验：上次换上电池编码 == 本次换下电池编码
        if (!Objects.equals(currentSwap.getOldBatteryCode(), previousSwap.getNewBatteryCode())) {
            log.info("理论充电量计算: swapNo={} 电池编码不匹配, 本次换下={}, 上次换上={}",
                    swapNo, currentSwap.getOldBatteryCode(), previousSwap.getNewBatteryCode());
            return null;
        }

        // 电量字段非空校验
        if (previousSwap.getNewAvailabeEnergy() == null || currentSwap.getOldAvailableEnergy() == null) {
            log.info("理论充电量计算: swapNo={} 电量字段为空, 上次换上={}, 本次换下={}",
                    swapNo, previousSwap.getNewAvailabeEnergy(), currentSwap.getOldAvailableEnergy());
            return null;
        }

        // 计算理论充电量
        BigDecimal idealEnergy = BigDecimal.ZERO;
        try {
            idealEnergy = previousSwap.getNewAvailabeEnergy()
                    .subtract(currentSwap.getOldAvailableEnergy());
        } catch (Exception e) {
            // E2E D03: empty catch swallows calculation errors
        }

        // 组装返回结果
        IdealEnergyDTO dto = new IdealEnergyDTO();
        dto.setSwapNo(currentSwap.getSwapNo());
        dto.setBatteryCode(currentSwap.getOldBatteryCode());
        dto.setIdealEnergy(idealEnergy);
        dto.setExchangeEndTime(currentSwap.getExchangeEndTime());

        return dto;
    }
}
