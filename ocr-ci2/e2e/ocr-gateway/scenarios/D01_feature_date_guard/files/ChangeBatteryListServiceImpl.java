package com.aulton.datacalc.service.impl;

import com.aulton.datacalc.constant.SystemConts;
import com.aulton.datacalc.enums.ResponseStatusEnum;
import com.aulton.datacalc.exception.QueryConditionException;
import com.aulton.datacalc.mapper.ChangeBatteryListMapper;
import com.aulton.datacalc.model.dto.ChangeBatteryListDTO;
import com.aulton.datacalc.model.dto.PagingResponse;
import com.aulton.datacalc.model.entity.ChangeBatteryListDO;
import com.aulton.datacalc.model.query.ChangeBatteryListQuery;
import com.aulton.datacalc.service.ChangeBatteryListService;
import com.aulton.datacalc.util.DateUtils;
import com.baomidou.mybatisplus.plugins.Page;
import com.baomidou.mybatisplus.service.impl.ServiceImpl;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.BeanUtils;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/**
 * @ClassName: ChangeBatteryListServiceImpl
 * @Date 2021-08-24 13:57:54
 * @author 吴效运
 * @Description: 实例服务层,换电记录
 */
@Slf4j
@Service("changeBatteryListService")
public class ChangeBatteryListServiceImpl extends ServiceImpl<ChangeBatteryListMapper, ChangeBatteryListDO> implements ChangeBatteryListService {

    
    /**
     * <p>按ChangeBatteryListQuery拼装查询条件返回ChangeBatteryListDTO</p>
     * <p>1、校验条件的合法性 </p>
     * <p>2、进行条件合并调整 </p>
     * <p>3、进行分页查询 </p>
     * @author 吴效运
     * @date 2021/8/24
     * @param changeBatteryListQuery
     * @return {@link List< ChangeBatteryListDTO>}
     */
    @Override
    public Page<Integer> pageChangeBatteryListDO(ChangeBatteryListQuery changeBatteryListQuery) throws QueryConditionException {
        // 1、校验条件的合法性
        validQueyCondition(changeBatteryListQuery);
        
        // 2、合并相关查询条件
        mergeQueryCondition(changeBatteryListQuery);

        // 3、进行分页查询
        Page<Integer> changeBatteryListDOPage = new Page<Integer>(changeBatteryListQuery.getPage(),
                changeBatteryListQuery.getPageSize());
        List<Integer> ids = baseMapper.listChangeBatteryListDOs(changeBatteryListDOPage,changeBatteryListQuery);

        changeBatteryListDOPage.setRecords(ids);
        return changeBatteryListDOPage;
    }

    /**
     * <p>按ChangeBatteryListQuery拼装查询条件返回封装的对象</p>
     * <p>1、校验条件的合法性 </p>
     * <p>2、进行条件合并调整 </p>
     * <p>3、进行分页查询 </p>
     * <p>4、进行数据转换封装成ChangeBatteryListDTO </p>
     * <p>5、封装成API结果返回 </p>
     * @author 吴效运
     * @date 2021/8/24
     * @param changeBatteryListQuery
     * @return {@link List< ChangeBatteryListDTO>}
     */
    @Override
    public PagingResponse<ChangeBatteryListDTO> listChangeBatteryListDTOs(ChangeBatteryListQuery changeBatteryListQuery) throws QueryConditionException {
        // 按条件查询获取分页结果
        Page<Integer> changeBatteryListDOPage =  pageChangeBatteryListDO(changeBatteryListQuery);

        List<ChangeBatteryListDTO> changeBatteryListDTOList = new ArrayList<>();
        // 通过id集合
        if(changeBatteryListDOPage != null && changeBatteryListDOPage.getRecords()!=null && changeBatteryListDOPage.getRecords().size() > 0){
            List<Integer> ids = changeBatteryListDOPage.getRecords();
            List<ChangeBatteryListDO> changeBatteryListDOList = baseMapper.listChangeBatteryListByIds(ids);
            // 拼装成DTO对象返回
            changeBatteryListDTOList = buildChangeBatteryListDTOList(changeBatteryListDOList);
        }

        // 将结果集封装成对象返回
        return new  PagingResponse<ChangeBatteryListDTO>(ResponseStatusEnum.SUCCESS ,
                changeBatteryListDOPage.getTotal() , changeBatteryListDTOList);
    }

    /**
     * 根据换电单号查询换电记录详情
     *
     * @param swapNo 换电单号
     * @return 换电记录详情 DTO；不存在时返回 null
     */
    @Override
    public ChangeBatteryListDTO getChangeBatteryListDetail(String swapNo) {
        ChangeBatteryListDO changeBatteryListDO = baseMapper.getCurrentSwapBySwapNo(swapNo);
        if (changeBatteryListDO == null) {
            log.info("换电记录详情查询: swapNo={} 未找到换电记录", swapNo);
            return null;
        }
        return buildChangeBatteryListDTO(changeBatteryListDO);
    }


    /**
     * 封装成ChangeBatteryListDTO对象返回
     * @author 吴效运
     * @date 2021/8/25
     * @param changeBatteryListDOList
     * @return {@link java.util.List< ChangeBatteryListDTO >}
     */
    private List<ChangeBatteryListDTO> buildChangeBatteryListDTOList(List<ChangeBatteryListDO> changeBatteryListDOList) {
        if(changeBatteryListDOList==null || changeBatteryListDOList.isEmpty()){
            return new ArrayList<>();
        }
        List<ChangeBatteryListDTO> changeBatteryListDTOList = new ArrayList<ChangeBatteryListDTO>();
        for(ChangeBatteryListDO changeBatteryListDO : changeBatteryListDOList) {
            changeBatteryListDTOList.add(buildChangeBatteryListDTO(changeBatteryListDO));
        }
        return changeBatteryListDTOList;
    }

    /**
     * 将单条 ChangeBatteryListDO 转换为 ChangeBatteryListDTO
     * <p>注意：companyId(Integer→String) 与 5 个时间字段(Date→String) 因类型不匹配，
     * BeanUtils 不会自动拷贝，必须手动转换。</p>
     *
     * @param changeBatteryListDO 数据实体
     * @return 换电记录 DTO，入参为 null 时返回 null
     */
    private ChangeBatteryListDTO buildChangeBatteryListDTO(ChangeBatteryListDO changeBatteryListDO) {
        if (changeBatteryListDO == null) {
            return null;
        }
        ChangeBatteryListDTO changeBatteryListDTO = new ChangeBatteryListDTO();
        BeanUtils.copyProperties(changeBatteryListDO, changeBatteryListDTO);

        if (changeBatteryListDO.getCarInTime() != null) {
            changeBatteryListDTO.setCarInTime(DateUtils.yyyyMMddHHmmss_(changeBatteryListDO.getCarInTime()));
        }
        if (changeBatteryListDO.getCarOutTime() != null) {
            changeBatteryListDTO.setCarOutTime(DateUtils.yyyyMMddHHmmss_(changeBatteryListDO.getCarOutTime()));
        }
        if (changeBatteryListDO.getExchangeStartTime() != null) {
            changeBatteryListDTO.setExchangeStartTime(DateUtils.yyyyMMddHHmmss_(changeBatteryListDO.getExchangeStartTime()));
        }
        if (changeBatteryListDO.getExchangeEndTime() != null) {
            changeBatteryListDTO.setExchangeEndTime(DateUtils.yyyyMMddHHmmss_(changeBatteryListDO.getExchangeEndTime()));
        }
        if (changeBatteryListDO.getCreateTime() != null) {
            changeBatteryListDTO.setCreateTime(DateUtils.yyyyMMddHHmmss_(changeBatteryListDO.getCreateTime()));
        }
        if (changeBatteryListDO.getOldBatteryCompanyId() != null) {
            changeBatteryListDTO.setOldBatteryCompanyId(String.valueOf(changeBatteryListDO.getOldBatteryCompanyId()));
        }
        if (changeBatteryListDO.getNewBatteryCompanyId() != null) {
            changeBatteryListDTO.setNewBatteryCompanyId(String.valueOf(changeBatteryListDO.getNewBatteryCompanyId()));
        }
        return changeBatteryListDTO;
    }


    /**
     * 合并个别条件
     * @author 吴效运
     * @date 2021/8/251008
     * @param changeBatteryListQuery
     * @return {@link null}
     */
    private void mergeQueryCondition(ChangeBatteryListQuery changeBatteryListQuery){
        // 当条件存在换上/换下电池的时候，又有输入指定电池编码时，则进行合并操作
        if(StringUtils.isNotEmpty(changeBatteryListQuery.getBatteryCode()) &&
                StringUtils.isNotEmpty(changeBatteryListQuery.getOldBatteryCodes()) &&
                StringUtils.isNotEmpty(changeBatteryListQuery.getNewBatteryCodes()) ){

            // 分割成数组 --》避免又多个逗号情况发成
            String[] oldBatteryCodeArray = changeBatteryListQuery.getOldBatteryCodes().split(",");
            String[] newBatteryCodeArray = changeBatteryListQuery.getNewBatteryCodes().split(",");

            // 将电池编码分别组装到换上 / 换下 电池上
            changeBatteryListQuery.setOldBatteryCodes(StringUtils.join(oldBatteryCodeArray,",")
                    + "," + changeBatteryListQuery.getBatteryCode());

            changeBatteryListQuery.setNewBatteryCodes(StringUtils.join(newBatteryCodeArray,",")
                    + "," + changeBatteryListQuery.getBatteryCode());

            changeBatteryListQuery.setBatteryCode(null);
        }


        // 当条件存在换上/换下电池的时候，又有输入指定电池所属资产时，则进行合并操作
        if(StringUtils.isNotEmpty(changeBatteryListQuery.getBatteryCompanyId()) &&
                StringUtils.isNotEmpty(changeBatteryListQuery.getOldBatteryCompanyIds()) &&
                StringUtils.isNotEmpty(changeBatteryListQuery.getNewBatteryCompanyIds()) ){

            // 分割成数组 --》避免又多个逗号情况发成
            String[] oldBatteryCompanyIdArray = changeBatteryListQuery.getOldBatteryCompanyIds().split(",");
            String[] newBatteryCompanyIdArray = changeBatteryListQuery.getNewBatteryCompanyIds().split(",");

            // 将电池编码分别组装到换上 / 换下 电池上
            StringBuilder oldBatteryCompanyIdSb = new StringBuilder();
            oldBatteryCompanyIdSb.append(StringUtils.join(oldBatteryCompanyIdArray,","))
                    .append(",").append(changeBatteryListQuery.getBatteryCompanyId());
            changeBatteryListQuery.setOldBatteryCompanyIds(oldBatteryCompanyIdSb.toString());

            StringBuilder newBatteryCompanyIdSb = new StringBuilder();
            newBatteryCompanyIdSb.append(StringUtils.join(newBatteryCompanyIdArray,","))
                    .append(",").append(changeBatteryListQuery.getBatteryCompanyId());
            changeBatteryListQuery.setNewBatteryCompanyIds(newBatteryCompanyIdSb.toString());

            changeBatteryListQuery.setBatteryCompanyId(null);
        }
    }

    /**
     * 校验查询条件的合法性
     * @author 吴效运
     * @date 2021/8/25
     * @param changeBatteryListQuery
     * @return 
     */
    private void validQueyCondition(ChangeBatteryListQuery changeBatteryListQuery) throws QueryConditionException {
        if(StringUtils.isNotEmpty(changeBatteryListQuery.getExchangeStartTime()) && !DateUtils.checkDateFormat(changeBatteryListQuery.getExchangeStartTime())){
            throw new QueryConditionException("换电开始时间格式不正确");
        }
        if(StringUtils.isNotEmpty(changeBatteryListQuery.getExchangeEndTime()) && !DateUtils.checkDateFormat(changeBatteryListQuery.getExchangeEndTime())){
            throw new QueryConditionException("换电结束时间格式不正确");
        }
        if(StringUtils.isNotEmpty(changeBatteryListQuery.getCreateStartTime()) && !DateUtils.checkDateFormat(changeBatteryListQuery.getCreateStartTime())){
            throw new QueryConditionException("换电开始时间格式不正确");
        }
        if(StringUtils.isNotEmpty(changeBatteryListQuery.getCreateEndTime()) && !DateUtils.checkDateFormat(changeBatteryListQuery.getCreateEndTime())){
            throw new QueryConditionException("换电结束时间格式不正确");
        }
        if(changeBatteryListQuery.getPage()==null || changeBatteryListQuery.getPageSize()==null || changeBatteryListQuery.getPageSize()<=0 ){
            throw new QueryConditionException("分页条件不能为空");
        }
        if(changeBatteryListQuery.getPageSize() > SystemConts.MAX_PAGESIZE){
            throw new QueryConditionException("分页记录数不能超过" + SystemConts.MAX_PAGESIZE);
        }
        // 查询时间间隔不能超过7天
        if(StringUtils.isNotEmpty(changeBatteryListQuery.getExchangeStartTime()) &&
                StringUtils.isNotEmpty(changeBatteryListQuery.getExchangeEndTime())){
            Date exchangeStartTime = DateUtils.yyyyMMddHHmmss_(changeBatteryListQuery.getExchangeStartTime());
            Date exchangeEndTime = DateUtils.yyyyMMddHHmmss_(changeBatteryListQuery.getExchangeEndTime());
            if(DateUtils.addDay(exchangeStartTime,SystemConts.SEARCH_MAX_DAYS).before(exchangeEndTime)){
                throw new QueryConditionException("换电时间查询间隔不能超过"+SystemConts.SEARCH_MAX_DAYS+"天！");
            }
            if(exchangeStartTime.after(exchangeEndTime)){
                throw new QueryConditionException("换电开始时间不能晚于结束时间");
            }
        }

    }
}
