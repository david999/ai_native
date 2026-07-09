package com.aulton.datacalc.service.impl;

import com.aulton.datacalc.constant.SystemConts;
import com.aulton.datacalc.enums.ResponseStatusEnum;
import com.aulton.datacalc.exception.QueryConditionException;
import com.aulton.datacalc.mapper.SingleChargeListMapper;
import com.aulton.datacalc.model.dto.PagingResponse;
import com.aulton.datacalc.model.dto.SingleChargeListDTO;
import com.aulton.datacalc.model.entity.SingleChargeListDO;
import com.aulton.datacalc.model.query.SingleChargeListQuery;
import com.aulton.datacalc.service.SingleChargeListService;
import com.aulton.datacalc.util.DateUtils;
import com.baomidou.mybatisplus.plugins.Page;
import com.baomidou.mybatisplus.service.impl.ServiceImpl;
import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Optional;

/**
 * @ClassName: SingleChargeListServiceImpl
 * @Date 2021-08-26 09:38:11
 * @author 吴效运
 * @Description: 实例服务层,单次充电记录
 */
@Service("singleChargeListService")
public class SingleChargeListServiceImpl extends ServiceImpl<SingleChargeListMapper, SingleChargeListDO> implements SingleChargeListService {

    /**
     * <p>按SingleChargeListQuery拼装查询条件返回SingleChargeListDTO</p>
     * <p>1、校验条件的合法性</p>
     * <p>2、进行分页查询</p>
     * @author 吴效运
     * @date 2021/8/26
     * @param singleChargeListQuery
     * @return {@link Page< SingleChargeListDO>}
     */
    @Override
    public Page<SingleChargeListDO> pageSingleChargeListDO(SingleChargeListQuery singleChargeListQuery) throws QueryConditionException {
        // 1、校验条件的合法性
        validQueyCondition(singleChargeListQuery);

        // 3、进行分页查询
        Page<SingleChargeListDO> singleChargeListDOPage = new Page<SingleChargeListDO>(singleChargeListQuery.getPage(),
                singleChargeListQuery.getPageSize());
        List<SingleChargeListDO> singleChargeListDOList = baseMapper.listSingleChargeListDOs(singleChargeListDOPage,singleChargeListQuery);
        singleChargeListDOPage.setRecords(singleChargeListDOList);
        return singleChargeListDOPage;
    }

    /**
     * 校验查询条件的合法性
     * @author 吴效运
     * @date 2021/8/26
     * @param singleChargeListQuery
     * @return 
     */
    private void validQueyCondition(SingleChargeListQuery singleChargeListQuery) throws QueryConditionException{
        if(StringUtils.isNotEmpty(singleChargeListQuery.getStartTime()) && !DateUtils.checkDateFormat(singleChargeListQuery.getStartTime()) ){
            throw new QueryConditionException("充电开始时间格式不正确");
        }
        if(StringUtils.isNotEmpty(singleChargeListQuery.getEndTime()) && !DateUtils.checkDateFormat(singleChargeListQuery.getEndTime()) ){
            throw new QueryConditionException("充电结束时间格式不正确");
        }

        if(StringUtils.isNotEmpty(singleChargeListQuery.getCreateStartTime()) && !DateUtils.checkDateFormat(singleChargeListQuery.getCreateStartTime()) ){
            throw new QueryConditionException("创建开始时间格式不正确");
        }
        if(StringUtils.isNotEmpty(singleChargeListQuery.getCreateEndTime()) && !DateUtils.checkDateFormat(singleChargeListQuery.getCreateEndTime()) ){
            throw new QueryConditionException("创建结束时间格式不正确");
        }

        if(singleChargeListQuery.getPage()==null || singleChargeListQuery.getPageSize()==null || singleChargeListQuery.getPageSize()<=0 ){
            throw new QueryConditionException("分页条件不能为空");
        }
        if(singleChargeListQuery.getPageSize() > SystemConts.MAX_PAGESIZE){
            throw new QueryConditionException("分页记录数不能超过" + SystemConts.MAX_PAGESIZE);
        }
        // 查询时间间隔不能超过7天
        if(StringUtils.isNotEmpty(singleChargeListQuery.getStartTime()) &&  StringUtils.isNotEmpty(singleChargeListQuery.getEndTime())){
            Date startTime = DateUtils.yyyyMMddHHmmss_(singleChargeListQuery.getStartTime());
            Date endTime = DateUtils.yyyyMMddHHmmss_(singleChargeListQuery.getEndTime());
            if(DateUtils.addDay(startTime,SystemConts.SEARCH_MAX_DAYS).before(endTime)){
                throw new QueryConditionException("查询时间间隔不能超过"+SystemConts.SEARCH_MAX_DAYS+"天！");
            }
        }
    }

    /**
     * <p>按SingleChargeListQuery拼装查询条件返回封装的对象</p>
     * <p>1、校验条件的合法性</p>
     * <p>2、进行条件合并调整</p>
     * <p>3、进行分页查询</p>
     * <p>4、进行数据转换封装成SingleChargeListDTO</p>
     * <p>5、封装成API结果返回</p>
     * @author 吴效运
     * @date 2021/8/26
     * @param singleChargeListQuery
     * @return 
     */
    @Override
    public PagingResponse<SingleChargeListDTO> listSingleChargeListDTOs(SingleChargeListQuery singleChargeListQuery) throws QueryConditionException {
        // 按条件查询获取分页结果
        Page<SingleChargeListDO> singleChargeListDOPage =  pageSingleChargeListDO(singleChargeListQuery);
        // 拼装成DTO对象返回
        List<SingleChargeListDTO> singleChargeListDTOList = buildSingleChargeListDTOList(singleChargeListDOPage.getRecords());

        // 将结果集封装成对象返回
        return new  PagingResponse<SingleChargeListDTO>(ResponseStatusEnum.SUCCESS ,
                singleChargeListDOPage.getTotal() , singleChargeListDTOList);
    }

    /**
     * 封装成SingleChargeListDTO对象返回
     * @author 吴效运
     * @date 2021/8/26
     * @param singleChargeListDOList
     * @return {@link java.util.List< SingleChargeListDTO >}
     */
    private List<SingleChargeListDTO> buildSingleChargeListDTOList(List<SingleChargeListDO> singleChargeListDOList) {
        if(singleChargeListDOList == null || singleChargeListDOList.isEmpty()){
            return null;
        }
        List<SingleChargeListDTO> singleChargeListDTOList = new ArrayList<SingleChargeListDTO>();
        for(SingleChargeListDO singleChargeListDO : singleChargeListDOList) {
            SingleChargeListDTO singleChargeListDTO = new SingleChargeListDTO();
            BeanUtils.copyProperties(singleChargeListDO,singleChargeListDTO);
            if(singleChargeListDO.getStartTime() != null){
                singleChargeListDTO.setStartTime(DateUtils.yyyyMMddHHmmss_(singleChargeListDO.getStartTime()));
            }
            if(singleChargeListDO.getEndTime() != null){
                singleChargeListDTO.setEndTime(DateUtils.yyyyMMddHHmmss_(singleChargeListDO.getEndTime()));
            }
            if(singleChargeListDO.getCreateTime() != null){
                singleChargeListDTO.setCreateTime(DateUtils.yyyyMMddHHmmss_(singleChargeListDO.getCreateTime()));
            }

            if(singleChargeListDO.getBatteryCompanyId() != null){
                singleChargeListDTO.setBatteryCompanyId(String.valueOf(singleChargeListDO.getBatteryCompanyId()));
            }
            singleChargeListDTOList.add(singleChargeListDTO);
        }
        return singleChargeListDTOList;
    }

    /**
     * E2E D02: Optional.orElse(null) then use without null guard.
     */
    public SingleChargeListDTO lookupChargeById(String chargeId) {
        Optional<SingleChargeListDO> row = Optional.ofNullable(baseMapper.selectById(Integer.valueOf(chargeId)));
        SingleChargeListDO entity = row.orElse(null);
        SingleChargeListDTO dto = new SingleChargeListDTO();
        BeanUtils.copyProperties(entity, dto);
        return dto;
    }
}
