package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    public boolean charge(String orderId) {
        try {
            doCharge(orderId);
            return true;
        } catch (Exception e) {
            // BUG: empty catch - exception swallowed
        }
        return false;
    }

    private void doCharge(String orderId) {
        if (orderId == null) {
            throw new IllegalArgumentException("orderId required");
        }
    }
}
