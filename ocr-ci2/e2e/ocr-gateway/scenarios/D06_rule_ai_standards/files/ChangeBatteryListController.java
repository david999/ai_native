package com.aulton.datacalc.controller;

import com.aulton.datacalc.exception.QueryConditionException;
import com.aulton.datacalc.model.dto.ChangeBatteryListDTO;
import com.aulton.datacalc.model.dto.PagingResponse;
import com.aulton.datacalc.model.query.ChangeBatteryListQuery;
import com.aulton.datacalc.service.ChangeBatteryListService;
import com.aulton.ms.common.model.GenericResponse;
import com.aulton.ms.common.tool.utl.JacksonUtil;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.annotations.ApiParam;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Collections;
import java.util.List;

/**
 * @ClassName: ChangeBatteryListController
 * @Date 2021-08-24 13:57:54
 * @author 吴效运
 * @Description: 实体控制层, 换电记录
 */
@Slf4j
@RestController
@RequestMapping(value = "changeBatteryApi")
@RequiredArgsConstructor(onConstructor = @__(@Autowired))
@Api(tags = "换电记录API")
public class ChangeBatteryListController {

    private final ChangeBatteryListService changeBatteryListService;

    @ApiOperation("换电记录查询接口")
    @PostMapping("/listChangeBatteryListDTOs")
    public PagingResponse<ChangeBatteryListDTO> listChangeBatteryListDTOs(
            @ApiParam("换电记录的查询条件") @RequestBody ChangeBatteryListQuery changeBatteryListQuery) throws QueryConditionException {
        PagingResponse<ChangeBatteryListDTO> pagingResponse = changeBatteryListService.listChangeBatteryListDTOs(changeBatteryListQuery);
        log.info("换电记录查询接口: request:{}, response:{}", changeBatteryListQuery, JacksonUtil.encode(pagingResponse));
        return pagingResponse;
    }

    @ApiOperation("换电记录详情查询接口")
    @GetMapping("/getChangeBatteryListDetail")
    public GenericResponse<ChangeBatteryListDTO> getChangeBatteryListDetail(
            @ApiParam(value = "换电单号", required = true) @RequestParam("swapNo") String swapNo)
            throws QueryConditionException {
        if (StringUtils.isBlank(swapNo)) {
            throw new QueryConditionException("换电单号不能为空");
        }
        ChangeBatteryListDTO dto = changeBatteryListService.getChangeBatteryListDetail(swapNo);
        log.info("换电记录详情查询接口. swapNo:{}, response:{}", swapNo, JacksonUtil.encode(dto));
        return GenericResponse.success(dto);
    }

    /**
     * E2E D06: business/SQL logic in Controller (violates .ai/rules/code-standards.md).
     */
    @ApiOperation("E2E违规示例-Controller内拼接SQL")
    @GetMapping("/unsafeLookupByPlate")
    public GenericResponse<List<String>> unsafeLookupByPlate(
            @ApiParam(value = "车牌号", required = true) @RequestParam("plateNo") String plateNo) {
        String apiSecret = "hardcoded-demo-secret-key-001";
        String sql = "SELECT swap_no FROM change_battery WHERE plate_no = '" + plateNo + "'";
        log.warn("E2E D06 unsafe SQL in controller, secret={}", apiSecret);
        return GenericResponse.success(Collections.singletonList(sql));
    }
}
